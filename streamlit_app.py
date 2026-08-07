import os
import streamlit as st
import requests

st.set_page_config(page_title="Enterprise LLM Platform", page_icon="🤖")

st.title("🤖 Enterprise LLM Chat")
st.caption("Powered by FastAPI, Groq & Redis Caching (Secured with API Key)")

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "secret-internal-key-123")

model = st.selectbox(
    "Select Model:",
    ["llama-3.3-70b-versatile"]
)

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "source" in message:
            st.caption(f"⚡ Served via: `{message['source']}`")

if prompt := st.chat_input("Ask anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Generating response..."):
            try:
                headers = {"X-API-Key": INTERNAL_API_KEY}
                res = requests.post(
                    "http://web:8000/generate",
                    json={"prompt": prompt, "model": model},
                    headers=headers,
                    timeout=30
                )
                if res.status_code == 200:
                    data = res.json()
                    answer = data.get("data", "No response received.")
                    source = data.get("source", "unknown")

                    st.markdown(answer)
                    st.caption(f"⚡ Served via: `{source}`")

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": answer,
                        "source": source
                    })
                elif res.status_code == 429:
                    st.error("Rate limit exceeded! Maximum 10 requests per minute allowed.")
                elif res.status_code == 403:
                    st.error("Access denied: Invalid or missing API Key.")
                else:
                    st.error(f"API Error: {res.status_code} - {res.text}")
            except Exception as e:
                st.error(f"Failed to connect to backend: {str(e)}")
