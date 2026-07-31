import os
from dotenv import load_dotenv
from google import genai  # <-- ADD THIS LINE

load_dotenv()

def main():
    print("Application started successfully!")

    # Initialize the Gemini client
    client = genai.Client()

    # Generate content using Gemini
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Give me a quick 1-sentence motivational quote for a software demo."
    )

    print("\n--- AI Model Response ---")
    print(response.text)

if __name__ == "__main__":
    main()