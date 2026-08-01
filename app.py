import os
from dotenv import load_dotenv
from google import genai
from google.genai.errors import ClientError
from groq import Groq

load_dotenv()

def main():
    print("Application started successfully!")

    # 1. DEFINE YOUR PROMPT HERE
    user_prompt = "Give me a 1-sentence motivation quote for a live demo."

    # 2. Try Gemini First
    print("\n--- Requesting Gemini ---")
    try:
        gemini_client = genai.Client()
        gemini_response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_prompt  # <--- Using prompt here
        )
        print("Gemini Response:", gemini_response.text)
        return  # Stop execution if Gemini succeeds!

    except ClientError as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            print("Gemini API rate limit reached (429). Falling back to Groq...")
        else:
            raise e

    # 3. Fallback to Groq ONLY if Gemini fails
    print("\n--- Requesting Groq (Fallback) ---")
    groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    groq_response = groq_client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": user_prompt,  # <--- Using the SAME prompt here
            }
        ],
        model="llama-3.3-70b-versatile",
    )
    print("Groq Response:", groq_response.choices[0].message.content)

if __name__ == "__main__":
    main()