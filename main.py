import os
import json
import hashlib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis
from groq import Groq

app = FastAPI()

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
cache = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class PromptPayload(BaseModel):
    prompt: str
    model: str = "llama-3.3-70b-versatile"

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

    try:
        completion = groq_client.chat.completions.create(
            model=payload.model,
            messages=[{"role": "user", "content": payload.prompt}],
        )
        response_data = completion.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM API Error: {str(e)}")

    try:
        cache.setex(cache_key, 3600, json.dumps(response_data))
    except redis.RedisError as err:
        print(f"Cache Write Warning: {err}")

    return {
        "source": "llm_api",
        "model": payload.model,
        "data": response_data
    }
