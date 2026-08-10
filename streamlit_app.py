import streamlit as st
import requests

st.set_page_config(page_title="AI Chat", layout="centered")
st.title("💬 Connected AI Chat")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display past messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Bottom chat input
if prompt := st.chat_input("Ask anything..."):
    # Render user prompt
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Prepare payload with entire conversation context
    payload = {"messages": st.session_state.messages}

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                res = requests.post("http://web:8000/chat", json=payload)
                if res.status_code == 200:
                    reply = res.json().get("response", "")
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                else:
                    st.error(f"Error {res.status_code}: {res.text}")
            except Exception as e:
                st.error(f"Connection failed: {e}")
