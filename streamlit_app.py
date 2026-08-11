import os
import requests
import streamlit as st

# Environment Configurations
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://app-web:8000/multi-agent-chat")
X_API_KEY = os.getenv("X_API_KEY", "secret-internal-key-123")

st.set_page_config(page_title="Enterprise Multi-Agent Workspace", page_icon="🤖", layout="wide")

st.title("🤖 Multi-Agent Llama 3.3 Enterprise Gateway")
st.caption("Orchestrating Autonomous AI Agents via Groq, CrewAI, and FastAPI")

# Initialize Session State for Chat History
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display Past Chat Messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if "agent_responses" in message:
            for resp in message["agent_responses"]:
                st.markdown(f"### {resp['agent_role']}")
                st.markdown(resp["output"])
                st.divider()
        else:
            st.markdown(message["content"])

# Process User Input
if prompt := st.chat_input("Enter a technical topic or request for the agent crew..."):
    # Render user prompt in UI
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Call FastAPI Multi-Agent Endpoint
    with st.chat_message("assistant"):
        with st.spinner("🤖 Agent Team Collaborating (Technical Researcher ➔ Technical Writer)..."):
            try:
                headers = {"X-API-KEY": X_API_KEY}
                payload = {"topic": prompt}

                response = requests.post(
                    FASTAPI_URL,
                    json=payload,
                    headers=headers,
                    timeout=120
                )

                if response.status_code == 200:
                    data = response.json()
                    agent_responses = data.get("agent_responses", [])

                    # Render each individual agent output explicitly
                    for resp in agent_responses:
                        st.markdown(f"### {resp['agent_role']}")
                        st.markdown(resp["output"])
                        st.divider()

                    # Save complete response array to session state
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": data.get("final_summary", ""),
                        "agent_responses": agent_responses
                    })
                else:
                    st.error(f"Backend API Error ({response.status_code}): {response.text}")

            except Exception as e:
                st.error(f"Connection Error: {str(e)}")