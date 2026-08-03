import os
import time
import logging
from dotenv import load_dotenv
import google.generativeai as genai
from groq import Groq

# Load environment variables
load_dotenv()

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Setup API Clients
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def generate_completion(prompt: str):
    start_time = time.time()
    
    # Feature 1: Structured Logs - Attempting Primary
    logging.info("🟢 [PRIMARY] Attempting request with Gemini 2.0 Flash...")
    
    try:
        # Primary Provider: Gemini
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        
        latency = round(time.time() - start_time, 2)
        
        # Feature 2: Provider Metrics
        print("\n" + "="*40)
        print(f"✅ SUCCESS | Provider: Gemini 2.0 Flash | Latency: {latency}s")
        print("="*40)
        return response.text

    except Exception as e:
        # Catch 429 Rate Limits or General Failures
        error_msg = str(e)
        logging.warning(f"🟡 [FAILOVER TRIGGERED] Primary provider failed. Error: {error_msg}")
        logging.info("🔴 [SECONDARY] Switching to Groq (Llama 3.3 70B)...")
        
        fallback_start = time.time()
        
        try:
            # Fallback Provider: Groq
            chat_completion = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
            )
            
            total_latency = round(time.time() - start_time, 2)
            fallback_latency = round(time.time() - fallback_start, 2)
            
            # Feature 2: Provider Metrics
            print("\n" + "="*40)
            print(f"✅ SUCCESS | Provider: Groq (Llama 3.3 70B)")
            print(f"⏱️  Fallback Latency: {fallback_latency}s | Total Latency: {total_latency}s")
            print("="*40)
            
            return chat_completion.choices[0].message.content

        except Exception as groq_error:
            logging.error(f"❌ [CRITICAL] Both primary and fallback providers failed: {groq_error}")
            raise groq_error

if __name__ == "__main__":
    test_prompt = "Explain quantum computing in two sentences."
    result = generate_completion(test_prompt)
    print(f"\nResponse Output:\n{result}")