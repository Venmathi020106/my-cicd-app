import os
from dotenv import load_dotenv
from google import genai
from google.genai.errors import ClientError
from groq import Groq

load_dotenv()

def main():
    print("Application started successfully!")

    # 1. Google Gemini Call
    print("\n--- Requesting Gemini ---")
    try:
        gemini_client = genai.Client()
        gemini_response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents="Give me a 1-sentence motivation quote for a live demo."
        )
        print("Gemini Response:", gemini_response.text)
    except ClientError as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            print("Gemini API rate limit reached (429). Bypassing to keep CI/CD green.")
        else:
            raise e

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