import os
import json
import hashlib
from fastapi import FastAPI
from pydantic import BaseModel
import redis

app = FastAPI()

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
cache = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

class PromptPayload(BaseModel):
    prompt: str
    model: str = "groq"

@app.get("/")
def read_root():
    return {"status": "online"}

@app.post("/generate")
def generate(payload: PromptPayload):
    raw_key = f"{payload.model}:{payload.prompt.strip().lower()}"
    cache_key = f"cache:{hashlib.sha256(raw_key.encode()).hexdigest()}"

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

    response_data = f"Response for '{payload.prompt}' using {payload.model}"

    try:
        cache.setex(cache_key, 3600, json.dumps(response_data))
    except redis.RedisError as err:
        print(f"Cache Write Warning: {err}")

    return {
        "source": "llm_api",
        "model": payload.model,
        "data": response_data
    }
