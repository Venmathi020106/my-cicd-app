<<<<<<< HEAD
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
=======
# app.py
def add(a, b):
    return a + b

def test_add():
    assert add(2, 3) == 5 # Fixed back to 5!
    print("Test Passed!")

if __name__ == "__main__":
    test_add()
>>>>>>> 99a55fe2f227549d9f82f3db8026b0539beba0eb
