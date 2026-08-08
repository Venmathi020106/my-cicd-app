import streamlit as st
import requests

st.set_page_config(page_title="Enterprise LLM Chat", layout="centered")

st.title("🤖 Enterprise LLM Chat")
st.caption("Powered by FastAPI, Groq & Redis Caching (Secured with API Key)")

# Model Selector
selected_model = st.selectbox("Select Model:", ["llama-3.3-70b-versatile"])

# 1. Initialize persistent state
if "messages" not in st.session_state:
    st.session_state.messages = []

# 2. Render past messages
chat_container = st.container()
with chat_container:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            if "source" in message:
                st.caption(f"⚡ Served via: `{message['source']}`")

# 3. Handle user input
if prompt := st.chat_input("Ask anything..."):
    # Append user prompt
    st.session_state.messages.append({"role": "user", "content": prompt})
    with chat_container:
        with st.chat_message("user"):
            st.write(prompt)

    # Format full message history payload for backend
    api_messages = [
        {"role": msg["role"], "content": msg["content"]} 
        for msg in st.session_state.messages
    ]

    url = "http://web:8000/generate"
    headers = {
        "X-API-Key": "secret-internal-key-123",
        "Content-Type": "application/json"
    }
    payload = {"messages": api_messages}

    with chat_container:
        with st.chat_message("assistant"):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    text = data.get("response", "No response received.")
                    source = data.get("source", "unknown")
                    
                    st.write(text)
                    st.caption(f"⚡ Served via: `{source}`")
                    
                    # Save assistant response to context
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": text,
                        "source": source
                    })
                else:
                    st.error(f"API Error: {response.status_code} - {response.text}")
            except Exception as e:
                st.error(f"Failed to connect to backend: {e}")