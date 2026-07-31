import os
import time
from dotenv import load_dotenv
from google import genai
from google.genai.errors import ClientError
from groq import Groq

load_dotenv()

def get_gemini_response(client):
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents="Give me a 1-sentence motivation quote for a live demo."
            )
            return response.text
        except ClientError as e:
            if "429" in str(e) and attempt < 2:
                print("Rate limit hit, waiting 5 seconds before retrying...")
                time.sleep(5)
            else:
                raise e

def main():
    print("Application started successfully!")

    print("\n--- Requesting Gemini ---")
    gemini_client = genai.Client()
    print("Gemini Response:", get_gemini_response(gemini_client))

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