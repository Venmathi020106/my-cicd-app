import streamlit as st
import requests

st.set_page_config(page_title="Enterprise LLM Chat", layout="centered")

st.title("🤖 Enterprise LLM Chat")
st.caption("Powered by FastAPI, Groq & Redis Caching (Secured with API Key)")

# Model Selector
selected_model = st.selectbox("Select Model:", ["llama-3.3-70b-versatile"])

# Chat Input
prompt = st.chat_input("Ask anything...")

if prompt:
    # Display user prompt
    with st.chat_message("user"):
        st.write(prompt)

    # API Request configuration
    url = "http://web:8000/generate"
    headers = {
        "X-API-Key": "secret-internal-key-123",
        "Content-Type": "application/json"
    }
    payload = {"prompt": prompt}

    with st.chat_message("assistant"):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                text = data.get("response", "No response received.")
                source = data.get("source", "unknown")
                
                # Display LLM text output
                st.write(text)
                
                # Display metadata tag
                st.caption(f"⚡ Served via: `{source}`")
            else:
                st.error(f"API Error: {response.status_code} - {response.text}")
        except Exception as e:
            st.error(f"Failed to connect to backend: {e}")