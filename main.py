import os
import json
import hashlib
import requests
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
import redis
from groq import Groq

app = FastAPI()

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
EXPECTED_API_KEY = os.getenv("INTERNAL_API_KEY", "secret-internal-key-123")
HF_TOKEN = os.getenv("HF_TOKEN", "")

cache = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def verify_api_key_and_rate_limit(api_key: str = Depends(api_key_header)):
    if api_key != EXPECTED_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API Key")

    rate_limit_key = f"rate_limit:{api_key}"
    try:
        current_requests = cache.incr(rate_limit_key)
        if current_requests == 1:
            cache.expire(rate_limit_key, 60)
        
        if current_requests > 10:
            raise HTTPException(
                status_code=429, 
                detail="Rate limit exceeded. Maximum 10 requests per minute allowed."
            )
    except redis.RedisError as err:
        print(f"Rate limiting warning: {err}")

    return api_key

class PromptPayload(BaseModel):
    prompt: str
    model: str = "llama-3.3-70b-versatile"

@app.get("/")
def read_root():
    return {"status": "online"}

@app.post("/generate", dependencies=[Depends(verify_api_key_and_rate_limit)])
def generate(payload: PromptPayload):
    raw_key = f"{payload.model}:{payload.prompt.strip().lower()}"
    cache_key = f"cache:{hashlib.sha256(raw_key.encode()).hexdigest()}"

    # 1. Check Redis Cache First
    try:
        cached_result = cache.get(cache_key)
        if cached_result:
            return {
                "source": "redis_cache",
                "model": payload.model,
                "data": json.loads(cached_result)
            }
    except redis.RedisError as err:
        print(f"Cache Read Warning: {err}")

    response_data = None
    provider_source = "primary_groq"

    # 2. Attempt Primary Provider (Groq)
    try:
        completion = groq_client.chat.completions.create(
            model=payload.model,
            messages=[{"role": "user", "content": payload.prompt}],
        )
        response_data = completion.choices[0].message.content
    except Exception as primary_error:
        print(f"[WARNING] Primary provider (Groq) failed: {primary_error}. Switching to Fallback...")
        provider_source = "fallback_huggingface"

        # 3. Attempt Secondary Provider (Hugging Face Router)
        try:
            hf_url = "https://router.huggingface.co/v1/chat/completions"
            headers = {
                "Content-Type": "application/json"
            }
            if HF_TOKEN:
                headers["Authorization"] = f"Bearer {HF_TOKEN}"

            hf_payload = {
                "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
                "messages": [{"role": "user", "content": payload.prompt}],
                "max_tokens": 500
            }

            hf_res = requests.post(hf_url, headers=headers, json=hf_payload, timeout=15)
            if hf_res.status_code == 200:
                response_data = hf_res.json()["choices"][0]["message"]["content"]
            else:
                response_data = f"[Fallback Mode - Mock] System operational. Primary Groq call failed."
        except Exception as fallback_error:
            raise HTTPException(
                status_code=500, 
                detail=f"Both Primary and Fallback LLM calls failed: {str(fallback_error)}"
            )

    # 4. Cache Final Result in Redis
    try:
        cache.setex(cache_key, 3600, json.dumps(response_data))
    except redis.RedisError as err:
        print(f"Cache Write Warning: {err}")

    return {
        "source": provider_source,
        "model": payload.model,
        "data": response_data
    }
