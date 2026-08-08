<<<<<<< HEAD
=======
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
    description="Production API Gateway with PII Guardrails, FAQ Pre-Caching, Redis Caching, Rate Limiting & Failover Orchestration.",
    version="1.1.0"
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
# 2. Feature 1: PII Sanitization Guardrail
# ------------------------------------------------------------------------------
def sanitize_prompt(prompt: str) -> tuple[str, bool]:
    """
    Scans and redacts sensitive PII data (Emails, Phone Numbers, Credit Cards, API Keys)
    from incoming prompts before hitting cache or LLMs.
    """
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
# 3. Feature 2: FAQ Pre-Caching Engine (Startup Event)
# ------------------------------------------------------------------------------
@app.on_event("startup")
async def seed_faq_cache():
    """Pre-populates Redis with common FAQs for instant zero-cost responses."""
    if not redis_client:
        logging.warning("Redis not connected. Skipping FAQ pre-caching.")
        return

    faqs = {
        "how do i reset my password?": "To reset your password, click on 'Forgot Password' on the login screen, enter your registered email, and follow the password reset link sent to your inbox.",
        "what are your support hours?": "Our technical support team is available 24/7 via live chat or by submitting a ticket through our developer portal.",
        "where can i find my api key?": "You can generate and manage your API keys inside your account dashboard under Settings > Developer Settings > API Keys."
    }

    for question, answer in faqs.items():
        clean_q, _ = sanitize_prompt(question)
        prompt_hash = hashlib.sha256(clean_q.strip().lower().encode("utf-8")).hexdigest()
        cache_key = f"cache:{prompt_hash}"
        
        try:
            # Set permanently or long TTL without overwriting existing runtime cache
            redis_client.set(cache_key, answer)
            logging.info(f"⚡ [FAQ PRE-CACHE] Seeded FAQ entry: '{question}'")
        except redis.RedisError as e:
            logging.error(f"Failed to seed FAQ '{question}': {e}")

# ------------------------------------------------------------------------------
# 4. Security & Rate Limiting Middleware
# ------------------------------------------------------------------------------
def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Validates the client API Key header."""
    if not x_api_key or x_api_key != X_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing X-API-Key header.")
    return x_api_key

def enforce_rate_limit(api_key: str, max_requests: int = 10, window_seconds: int = 60):
    """Enforces rate limiting using Redis atomic counters."""
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
# 5. LLM Provider Execution Callables
# ------------------------------------------------------------------------------
def call_groq_primary(prompt: str) -> str:
    """Calls primary model: Groq (Llama 3.3 70B)."""
    if not groq_client:
        raise Exception("Groq API client is not configured.")
    completion = groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile"
    )
    return completion.choices[0].message.content

def call_huggingface_fallback(prompt: str) -> str:
    """Calls secondary model fallback: Hugging Face Serverless Router (Qwen2.5-Coder)."""
    if not HF_TOKEN:
        raise Exception("Hugging Face API token is missing.")
    url = "https://api-inference.huggingface.co/models/Qwen/Qwen2.5-Coder-32B-Instruct"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {
        "inputs": f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n",
        "parameters": {"max_new_tokens": 512, "temperature": 0.7}
    }
    response = requests.post(url, headers=headers, json=payload, timeout=20)
    if response.status_code != 200:
        raise Exception(f"Hugging Face API Error ({response.status_code}): {response.text}")
    res_data = response.json()
    if isinstance(res_data, list) and "generated_text" in res_data[0]:
        return res_data[0]["generated_text"].split("<|im_start|>assistant\n")[-1].strip()
    return str(res_data)

# ------------------------------------------------------------------------------
# 6. Core REST Endpoint: /generate
# ------------------------------------------------------------------------------
@app.post("/generate")
async def generate_response(
    payload: PromptRequest,
    api_key: str = Depends(verify_api_key)
):
    # Step A: Enforce Rate Limiting
    enforce_rate_limit(api_key)

    # Step B: Apply Data Privacy & PII Guardrail
    original_prompt = payload.prompt
    clean_prompt, pii_found = sanitize_prompt(original_prompt)

    if pii_found:
        logging.info("🔒 [COMPLIANCE GUARDRAIL] Sensitive PII detected and redacted in request!")
        logging.info(f"🛡️  Cleaned Prompt: {clean_prompt}")

    # Step C: Check SHA-256 Redis Cache (Serves FAQs and previously cached queries)
    prompt_hash = hashlib.sha256(clean_prompt.strip().lower().encode("utf-8")).hexdigest()
    cache_key = f"cache:{prompt_hash}"

    if redis_client:
        try:
            cached_response = redis_client.get(cache_key)
            if cached_response:
                logging.info("⚡ [CACHE HIT] Response served directly from Redis.")
                return {
                    "response": cached_response.decode("utf-8"),
                    "source": "redis_cache",
                    "pii_redacted": pii_found
                }
        except redis.RedisError as e:
            logging.error(f"Redis cache fetch error: {e}")

    # Step D: Execute Primary LLM (Groq) with Fallback (Hugging Face)
    logging.info("🟢 [PRIMARY] Dispatching request to Groq LPU...")
    try:
        response_text = call_groq_primary(clean_prompt)
        source = "primary_groq"
    except Exception as primary_error:
        logging.warning(f"🟡 [FAILOVER TRIGGERED] Primary failed: {primary_error}")
        logging.info("🔴 [SECONDARY] Rerouting request to Hugging Face...")
        try:
            response_text = call_huggingface_fallback(clean_prompt)
            source = "fallback_huggingface"
        except Exception as fallback_error:
            logging.error(f"❌ [CRITICAL] All providers failed: {fallback_error}")
            raise HTTPException(
                status_code=502,
                detail="Bad Gateway: All primary and secondary LLM providers failed to respond."
            )

    # Step E: Cache Successful Response in Redis (1 Hour Expiration)
    if redis_client:
        try:
            redis_client.setex(cache_key, 3600, response_text)
            logging.info("💾 [CACHE STORED] Response saved in Redis with 3600s TTL.")
        except redis.RedisError as e:
            logging.error(f"Redis cache store error: {e}")

    return {
        "response": response_text,
        "source": source,
        "pii_redacted": pii_found
    }

# ------------------------------------------------------------------------------
# 7. Health Check Endpoint
# ------------------------------------------------------------------------------
@app.get("/health")
def health_check():
    redis_status = "connected" if redis_client and redis_client.ping() else "disconnected"
    return {
        "status": "healthy",
        "redis": redis_status,
        "primary_llm": "groq",
        "secondary_llm": "huggingface"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
>>>>>>> 5046e27 (feat: add automated FAQ pre-caching engine)
