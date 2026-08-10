from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict
from dotenv import load_dotenv
import os
import groq

load_dotenv()

app = FastAPI()
client = groq.Groq(api_key=os.getenv("GROQ_API_KEY"))

class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]  # Expects [{"role": "user"/"assistant", "content": "..."}]

@app.get("/")
def read_root():
    return {"status": "API is running"}

@app.post("/chat")
def chat(req: ChatRequest):
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=req.messages
        )
        return {
            "response": completion.choices[0].message.content,
            "model": "llama-3.3-70b-versatile"
        }
    except Exception as e:
        return {"response": f"Error: {str(e)}"}
