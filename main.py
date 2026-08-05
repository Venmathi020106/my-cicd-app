import os
import time
import requests
import redis
from fastapi import FastAPI, HTTPException, Query

app = FastAPI(title="Multi-LLM Orchestration Platform")

START_TIME = time.time()

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_API_TOKEN = os.getenv("HF_API_TOKEN")

try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_timeout=2)
except Exception:
    redis_client = None

@app.get("/")
def read_root():
    return {"message": "Multi-LLM Orchestration Platform API"}

@app.get("/metrics")
def get_metrics():
    redis_status = "disconnected"
    if redis_client:
        try:
            if redis_client.ping():
                redis_status = "connected"
        except Exception:
            redis_status = "error"

    uptime_seconds = int(time.time() - START_TIME)

    return {
        "status": "healthy",
        "uptime_seconds": uptime_seconds,
        "services": {
            "redis": redis_status,
            "primary_llm": "Hugging Face",
            "fallback_llm": "Groq"
        }
    }

@app.post("/generate")
def generate_text(prompt: str = Query(..., description="Prompt text to send to LLM")):
    errors = {}

    if HF_API_TOKEN:
        try:
            headers = {
                "Authorization": f"Bearer {HF_API_TOKEN}",
                "Content-Type": "application/json"
            }
            payload = {
                "inputs": prompt,
                "parameters": {"max_new_tokens": 100}
            }
            hf_res = requests.post(
                "https://api-inference.huggingface.co/models/gpt2",
                headers=headers,
                json=payload,
                timeout=8
            )
            if hf_res.status_code == 200:
                return {
                    "status": "success",
                    "provider": "Hugging Face",
                    "model": "gpt2",
                    "response": hf_res.json()
                }
            else:
                errors["huggingface"] = f"HTTP {hf_res.status_code}: {hf_res.text}"
        except Exception as e:
            errors["huggingface"] = str(e)
    else:
        errors["huggingface"] = "HF_API_TOKEN not found in environment"

    if GROQ_API_KEY:
        try:
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "model": "llama-3.1-8b-instant"
            }
            groq_res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=10
            )
            if groq_res.status_code == 200:
                return {
                    "status": "success",
                    "provider": "Groq",
                    "model": "llama-3.1-8b-instant",
                    "response": groq_res.json()
                }
            else:
                errors["groq"] = f"HTTP {groq_res.status_code}: {groq_res.text}"
        except Exception as e:
            errors["groq"] = str(e)
    else:
        errors["groq"] = "GROQ_API_KEY not found in environment"

    raise HTTPException(
        status_code=503,
        detail={
            "error": "All LLM providers failed to execute request",
            "diagnostics": errors
        }
    )
