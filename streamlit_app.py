import streamlit as st
import requests

st.set_page_config(page_title="Enterprise LLM Chat", layout="centered")

st.title("🤖 Enterprise LLM Chat")
st.caption("Powered by FastAPI, Groq & Redis Caching (Secured with API Key)")

# Model Selector
selected_model = st.selectbox("Select Model:", ["llama-3.3-70b-versatile"])

# Initialize Chat History in Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display previous chat messages from history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        if "source" in message:
            st.caption(f"⚡ Served via: `{message['source']}`")

# Accept new user prompt
prompt = st.chat_input("Ask anything...")

if prompt:
    # 1. Append & render user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # 2. Call FastAPI backend
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
                
                # Render response
                st.write(text)
                st.caption(f"⚡ Served via: `{source}`")
                
                # Append assistant message to history
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": text, 
                    "source": source
                })
            else:
                st.error(f"API Error: {response.status_code} - {response.text}")
        except Exception as e:
            st.error(f"Failed to connect to backend: {e}")