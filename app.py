import os
from dotenv import load_dotenv
from google import genai
from groq import Groq

# Load local environment variables from .env
load_dotenv()

def main():
    print("Application started successfully!")

    # 1. Google Gemini Call
    print("\n--- Requesting Gemini ---")
    gemini_client = genai.Client()
    gemini_response = gemini_client.models.generate_content(
        model="gemini-1.5-flash",  # <--- Changed model name here
        contents="Give me a 1-sentence motivation quote for a live demo."
    )
    print("Gemini Response:", gemini_response.text)

    # 2. Groq Call
    print("\n--- Requesting Groq ---")
    groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    groq_response = groq_client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": "Give me a 1-sentence tip for presenting a successful demo.",
            }
        ],
        model="llama-3.3-70b-versatile",
    )
    print("Groq Response:", groq_response.choices[0].message.content)

if __name__ == "__main__":
    main()