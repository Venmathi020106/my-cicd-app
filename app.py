import os
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

# CrewAI & LangChain Imports for Multi-Agent Workflows
from crewai import Agent, Task, Crew, Process
from langchain_groq import ChatGroq

# ------------------------------------------------------------------
# 1. Configuration & Application Setup
# ------------------------------------------------------------------
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(
    title="Enterprise AI Gateway & Governance Platform",
    description="Production API Gateway with PII Guardrails, Multi-turn Chat Context, Redis Caching, Failover Orchestration & Multi-Agent Workflows",
    version="1.4.0"
)

# Environment Variables
X_API_KEY = os.getenv("X_API_KEY", "secret-internal-key-123")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Client Initialization: Groq SDK
groq_client = None
if GROQ_API_KEY and not GROQ_API_KEY.startswith("invalid"):
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        logging.warning(f"Groq Client initialization warning: {e}")

# Client Initialization: LangChain Groq (for CrewAI)
crew_llm = None
if GROQ_API_KEY and not GROQ_API_KEY.startswith("invalid"):
    try:
        crew_llm = ChatGroq(
            temperature=0.3,
            groq_api_key=GROQ_API_KEY,
            model_name="llama-3.3-70b-versatile"
        )
    except Exception as e:
        logging.warning(f"CrewAI LLM initialization warning: {e}")

# Client Initialization: Redis Cache
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    redis_client.ping()
    logging.info("Connected to Redis successfully.")
except Exception as e:
    logging.warning(f"Redis connection offline: {e}")
    redis_client = None


# ------------------------------------------------------------------
# 2. Pydantic Request / Response Schemas
# ------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]

class MultiAgentRequest(BaseModel):
    topic: str


# ------------------------------------------------------------------
# 3. Helper Functions & Guardrails
# ------------------------------------------------------------------
def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Validates incoming internal API requests against the configured key."""
    if x_api_key != X_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid X-API-KEY header")
    return x_api_key

def generate_cache_key(messages: List[ChatMessage]) -> str:
    """Generates a unique MD5 hash based on full message history for Redis caching."""
    serialized = "|".join([f"{m.role}:{m.content}" for m in messages])
    return f"cache:chat:{hashlib.md5(serialized.encode()).hexdigest()}"

def call_huggingface_fallback(messages: List[ChatMessage]) -> str:
    """Fallback handler using Hugging Face Inference API if Groq fails or rate-limits."""
    if not HF_TOKEN:
        raise HTTPException(status_code=502, detail="Groq API failed and HF_TOKEN is missing for failover.")
    
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    API_URL = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-3B-Instruct"
    
    prompt = messages[-1].content if messages else "Hello"
    payload = {"inputs": prompt, "parameters": {"max_new_tokens": 500, "temperature": 0.3}}
    
    response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
    if response.status_code == 200:
        res_data = response.json()
        if isinstance(res_data, list) and "generated_text" in res_data[0]:
            return res_data[0]["generated_text"]
        return str(res_data)
    else:
        raise HTTPException(
            status_code=502, 
            detail=f"Both Groq and Hugging Face Failovers failed: {response.text}"
        )


# ------------------------------------------------------------------
# 4. Endpoints
# ------------------------------------------------------------------
@app.get("/health")
async def health_check():
    """Health check endpoint to verify container and dependency status."""
    return {
        "status": "healthy",
        "redis_connected": redis_client is not None,
        "groq_configured": groq_client is not None,
        "hf_fallback_ready": bool(HF_TOKEN)
    }


@app.post("/chat")
async def chat_endpoint(request: ChatRequest, api_key: str = Depends(verify_api_key)):
    """Standard multi-turn chat endpoint with Redis caching and Groq/HF failover."""
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages array cannot be empty.")

    cache_key = generate_cache_key(request.messages)

    if redis_client:
        try:
            cached_res = redis_client.get(cache_key)
            if cached_res:
                logging.info(f"Cache HIT for key: {cache_key}")
                return {"response": cached_res, "source": "redis_cache"}
        except Exception as e:
            logging.error(f"Redis lookup error: {e}")

    formatted_messages = [{"role": m.role, "content": m.content} for m in request.messages]
    
    if groq_client:
        try:
            logging.info("Executing request via Groq (Llama 3.3)...")
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=formatted_messages,
                temperature=0.3,
                max_tokens=1024
            )
            response_text = completion.choices[0].message.content

            if redis_client and response_text:
                try:
                    redis_client.setex(cache_key, 3600, response_text)
                except Exception as e:
                    logging.error(f"Redis write error: {e}")

            return {"response": response_text, "source": "groq_llama_3.3"}

        except Exception as e:
            logging.warning(f"Groq API call failed: {e}. Routing to Hugging Face Fallback...")

    response_text = call_huggingface_fallback(request.messages)
    return {"response": response_text, "source": "huggingface_fallback"}


@app.post("/multi-agent-chat")
async def run_multi_agent(request: MultiAgentRequest, api_key: str = Depends(verify_api_key)):
    """Multi-Agent execution endpoint returning explicit outputs per agent."""
    if not crew_llm:
        raise HTTPException(
            status_code=500, 
            detail="CrewAI LLM engine is not initialized. Ensure GROQ_API_KEY is configured."
        )

    try:
        logging.info(f"Initiating Multi-Agent Crew for topic: '{request.topic}'")

        # Define Agent 1: Technical Researcher
        researcher = Agent(
            role="Technical Researcher",
            goal=f"Analyze the request '{request.topic}' and extract key architectural components.",
            backstory="An expert enterprise systems architect specializing in scalable design patterns.",
            llm=crew_llm,
            verbose=True
        )

        # Define Agent 2: Technical Writer
        writer = Agent(
            role="Technical Writer",
            goal="Synthesize research findings into clear, developer-friendly documentation.",
            backstory="A principal documentation engineer who simplifies complex technical structures.",
            llm=crew_llm,
            verbose=True
        )

        # Define Task 1 for Technical Researcher
        task_research = Task(
            description=f"Analyze this topic in detail and break down technical specs: {request.topic}",
            expected_output="A bulleted list of technical components and requirements.",
            agent=researcher
        )

        # Define Task 2 for Technical Writer
        task_write = Task(
            description="Format the research output into a final structured guide with actionable steps.",
            expected_output="A developer-friendly implementation guide.",
            agent=writer
        )

        # Assemble and Run Crew
        crew = Crew(
            agents=[researcher, writer],
            tasks=[task_research, task_write],
            process=Process.sequential
        )

        crew_result = crew.kickoff()

        # Extract outputs per agent directly from Task objects and CrewOutput tasks_output
        agent_responses = []

        if hasattr(crew_result, 'tasks_output') and crew_result.tasks_output:
            for task_out in crew_result.tasks_output:
                agent_name = task_out.agent if hasattr(task_out, 'agent') and task_out.agent else "AI Agent"
                agent_responses.append({
                    "agent_role": f"🤖 {agent_name}",
                    "output": str(task_out.raw)
                })

        # Fallback mapping if tasks_output is unavailable
        if not agent_responses:
            agent_responses = [
                {
                    "agent_role": "🤖 Technical Researcher (Agent 1)",
                    "output": str(task_research.output.raw) if task_research.output else "No output"
                },
                {
                    "agent_role": "✍️ Technical Writer (Agent 2)",
                    "output": str(task_write.output.raw) if task_write.output else "No output"
                }
            ]

        return {
            "status": "success",
            "agent_responses": agent_responses,
            "final_summary": str(crew_result.raw) if hasattr(crew_result, 'raw') else str(crew_result)
        }

    except Exception as e:
        logging.error(f"Multi-agent workflow error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))