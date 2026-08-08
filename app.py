import os
import re
import time
import hashlib
import logging
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Depends
from pydantic import BaseModel
import redis
import requests
from groq import Groq

# ------------------------------------------------------------------------------
# 1. Configuration & Setup
# ------------------------------------------------------------------------------
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(
    title="Enterprise AI Gateway & Governance Platform",
    description="Production API Gateway with PII Guardrails, FAQ Pre-Caching, Redis Caching & Failover Orchestration.",
    version="1.2.0"
)

# Environment Variables
X_API_KEY = os.getenv("X_API_KEY", "secret-internal-key-123")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Client Initialization
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=False)
    redis_client.ping()
    logging.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    logging.warning(f"Redis connection failed: {e}. Operating without cache/rate limiting.")
    redis_client = None

# Request Data Models
class PromptRequest(BaseModel):
    prompt: str

# ------------------------------------------------------------------------------
# 2. PII Sanitization Guardrail
# ------------------------------------------------------------------------------
def sanitize_prompt(prompt: str) -> tuple[str, bool]:
    pii_patterns = {
        "EMAIL": r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+',
        "PHONE": r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
        "CREDIT_CARD": r'\b(?:\d[ -]*?){13,16}\b',
        "API_KEY_SECRET": r'(?i)(api[_-]?key|secret|bearer|token)\s*[:=]\s*["\']?[a-zA-Z0-9_\-]{16,}["\']?'
    }
    cleaned_prompt = prompt
    pii_detected = False

    for pii_type, pattern in pii_patterns.items():
        if re.search(pattern, cleaned_prompt):
            pii_detected = True
            cleaned_prompt = re.sub(pattern, f"[REDACTED_{pii_type}]", cleaned_prompt)

    return cleaned_prompt, pii_detected

# ------------------------------------------------------------------------------
# 3. Security & Rate Limiting Helpers
# ------------------------------------------------------------------------------
def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if not x_api_key or x_api_key != X_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing X-API-Key header.")
    return x_api_key

def enforce_rate_limit(api_key: str, max_requests: int = 10, window_seconds: int = 60):
    if not redis_client:
        return
    rate_key = f"rate_limit:{api_key}"
    try:
        current_requests = redis_client.incr(rate_key)
        if current_requests == 1:
            redis_client.expire(rate_key, window_seconds)
        if current_requests > max_requests:
            ttl = redis_client.ttl(rate_key)
            raise HTTPException(
                status_code=429,
                detail=f"Too Many Requests: Rate limit exceeded. Try again in {ttl} seconds."
            )
    except redis.RedisError as e:
        logging.error(f"Redis rate limiting error: {e}")

# ------------------------------------------------------------------------------
# 4. LLM Provider Execution Callables
# ------------------------------------------------------------------------------
def call_groq_primary(prompt: str) -> str:
    """Calls primary model: Groq (Llama 3.3 70B)."""
    if not groq_client:
        raise Exception("Groq API client is not configured or key is invalid.")
    completion = groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile"
    )
    return completion.choices[0].message.content

def call_huggingface_fallback(prompt: str) -> str:
    """Calls secondary fallback: Hugging Face Serverless Router (Qwen2.5-Coder)."""
    if not HF_TOKEN:
        raise Exception("Hugging Face API token is missing.")
    
    url = "https://api-inference.huggingface.co/models/Qwen/Qwen2.5-Coder-32B-Instruct"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {
        "inputs": f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n",
        "parameters": {"max_new_tokens": 256, "temperature": 0.7}
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=20)
    if response.status_code != 200:
        raise Exception(f"Hugging Face API Error ({response.status_code}): {response.text}")
    
    res_data = response.json()
    if isinstance(res_data, list) and "generated_text" in res_data[0]:
        return res_data[0]["generated_text"].split("<|im_start|>assistant\n")[-1].strip()
    return str(res_data)

# ------------------------------------------------------------------------------
# 5. Core REST Endpoint: /generate
# ------------------------------------------------------------------------------
@app.post("/generate")
async def generate_response(
    payload: PromptRequest,
    api_key: str = Depends(verify_api_key)
):
    enforce_rate_limit(api_key)

    original_prompt = payload.prompt
    clean_prompt, pii_found = sanitize_prompt(original_prompt)

    prompt_hash = hashlib.sha256(clean_prompt.strip().lower().encode("utf-8")).hexdigest()
    cache_key = f"cache:{prompt_hash}"

    if redis_client:
        try:
            cached_response = redis_client.get(cache_key)
            if cached_response:
                return {
                    "response": cached_response.decode("utf-8"),
                    "source": "redis_cache",
                    "pii_redacted": pii_found
                }
        except redis.RedisError as e:
            logging.error(f"Redis fetch error: {e}")

    # Primary Attempt with Automatic Fallback
    logging.info("🟢 Attempting primary model (Groq)...")
    try:
        response_text = call_groq_primary(clean_prompt)
        source = "primary_groq"
    except Exception as primary_error:
        logging.warning(f"🟡 Primary Groq failed: {primary_error}. Rerouting to Hugging Face fallback...")
        try:
            response_text = call_huggingface_fallback(clean_prompt)
            source = "fallback_huggingface"
        except Exception as fallback_error:
            logging.error(f"❌ Fallback failed: {fallback_error}")
            raise HTTPException(
                status_code=502,
                detail=f"Bad Gateway: Primary and Fallback providers failed. Details: {fallback_error}"
            )

    if redis_client:
        try:
            redis_client.setex(cache_key, 3600, response_text)
        except redis.RedisError as e:
            logging.error(f"Redis store error: {e}")

    return {
        "response": response_text,
        "source": source,
        "pii_redacted": pii_found
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)