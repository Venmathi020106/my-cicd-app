import os
import re
import time
import hashlib
import logging
from typing import Optional, List, Dict
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Depends
from pydantic import BaseModel
import redis
import requests
from groq import Groq

# ------------------------------------------------------------------------------
# 1. Configuration & Application Setup
# ------------------------------------------------------------------------------
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(
    title="Enterprise AI Gateway & Governance Platform",
    description="Production API Gateway with PII Guardrails, Multi-turn Chat Context, Redis Caching & Failover Orchestration.",
    version="1.3.0"
)

# Environment Variables
X_API_KEY = os.getenv("X_API_KEY", "secret-internal-key-123")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Client Initialization
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY and not GROQ_API_KEY.startswith("invalid_") and not GROQ_API_KEY.startswith("invlaid_") else None

try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=False)
    redis_client.ping()
    logging.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    logging.warning(f"Redis connection failed: {e}. Operating without cache/rate limiting.")
    redis_client = None

# Pydantic Schemas for Multi-turn History
class MessageItem(BaseModel):
    role: str
    content: str

class PromptRequest(BaseModel):
    messages: List[MessageItem]

# ------------------------------------------------------------------------------
# 2. PII Guardrail & Security Helpers
# ------------------------------------------------------------------------------
def sanitize_prompt(prompt: str) -> tuple[str, bool]:
    """Scans and redacts sensitive data (emails, phones, cards, keys) from prompts."""
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

def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Validates header authorization key."""
    if not x_api_key or x_api_key != X_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing X-API-Key header.")
    return x_api_key

def enforce_rate_limit(api_key: str, max_requests: int = 10, window_seconds: int = 60):
    """Enforces sliding window rate limits using Redis."""
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
# 3. Execution Engines (Primary & Secondary Fallback)
# ------------------------------------------------------------------------------
def call_groq_primary(messages: List[Dict[str, str]]) -> str:
    """Primary LLM provider: Groq (Llama 3.3 70B) with full chat history."""
    if not groq_client:
        raise Exception("Groq client not initialized or invalid API key.")
    completion = groq_client.chat.completions.create(
        messages=messages,
        model="llama-3.3-70b-versatile"
    )
    return completion.choices[0].message.content

def call_huggingface_fallback(messages: List[Dict[str, str]]) -> str:
    """Secondary LLM provider fallback: Hugging Face Router API (Llama 3.2 1B)."""
    if not HF_TOKEN:
        raise Exception("Hugging Face API token (HF_TOKEN) is missing.")
    
    url = "https://router.huggingface.co/hf-inference/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {HF_TOKEN.strip()}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "meta-llama/Llama-3.2-1B-Instruct",
        "messages": messages,
        "max_tokens": 256
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=20)
    if response.status_code != 200:
        raise Exception(f"Hugging Face API Error ({response.status_code}): {response.text}")
    
    res_data = response.json()
    return res_data["choices"][0]["message"]["content"]

# ------------------------------------------------------------------------------
# 4. REST Endpoints
# ------------------------------------------------------------------------------
@app.get("/")
def read_root():
    return {"status": "online", "service": "Enterprise AI Gateway"}

@app.post("/generate")
async def generate_response(
    payload: PromptRequest,
    api_key: str = Depends(verify_api_key)
):
    enforce_rate_limit(api_key)

    # Sanitize each message in the context history
    formatted_messages = []
    pii_found = False
    for msg in payload.messages:
        if msg.role == "user":
            clean_content, pii_detected = sanitize_prompt(msg.content)
            if pii_detected:
                pii_found = True
            formatted_messages.append({"role": "user", "content": clean_content})
        else:
            formatted_messages.append({"role": msg.role, "content": msg.content})

    # Cache key generated based on full context sequence
    context_str = "".join([f"{m['role']}:{m['content']}" for m in formatted_messages])
    prompt_hash = hashlib.sha256(context_str.strip().lower().encode("utf-8")).hexdigest()
    cache_key = f"cache:{prompt_hash}"

    # Check Cache First
    if redis_client:
        try:
            cached_response = redis_client.get(cache_key)
            if cached_response and cached_response.decode("utf-8").strip():
                return {
                    "response": cached_response.decode("utf-8"),
                    "source": "redis_cache",
                    "pii_redacted": pii_found
                }
        except redis.RedisError as e:
            logging.error(f"Redis fetch error: {e}")

    # Primary Attempt with Automatic Fallback Rerouting
    logging.info("Attempting primary model (Groq)...")
    try:
        response_text = call_groq_primary(formatted_messages)
        source = "primary_groq"
    except Exception as primary_error:
        logging.warning(f"Primary Groq failed: {primary_error}. Rerouting to Hugging Face fallback...")
        try:
            response_text = call_huggingface_fallback(formatted_messages)
            source = "fallback_huggingface"
        except Exception as fallback_error:
            logging.error(f"Fallback failed: {fallback_error}")
            raise HTTPException(
                status_code=502,
                detail=f"Bad Gateway: Primary and Fallback providers failed. Details: {fallback_error}"
            )

    # Store in Cache only if response is non-empty
    if redis_client and response_text and response_text.strip():
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