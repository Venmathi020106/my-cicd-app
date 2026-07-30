import os
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    print("Error: GROQ_API_KEY is not set in .env")
else:
    print("--- Running Groq Agent ---")
    llm = ChatGroq(model_name="llama-3.1-8b-instant", groq_api_key=api_key)
    response = llm.invoke("Hello, Groq! Confirm you are active.")
    print("Agent Response:", response.content)