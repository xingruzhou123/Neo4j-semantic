"""
Main Streamlit chatbot application.
A chatbot for querying research project data from Neo4j.
"""

import streamlit as st
from utils import write_message
from agent import generate_response, memory

# Page Config
st.set_page_config(
    page_title="Research Assistant",
    page_icon=":microscope:",
    layout="wide"
)

# Title
st.title(":microscope: Research Project Assistant")
st.markdown("Ask me about research projects, datasets, team members, and more!")

# Clear Memory Button in sidebar
with st.sidebar:
    st.header("Settings")
    if st.button("Clear Chat Memory"):
        memory.clear()
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Memory cleared! How can I help you?"
            },
        ]
        st.rerun()

# Set up Session State
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hi! I'm your Research Project Assistant. I can help you explore the research database. You can ask me about:\n\n"
                       "- Research projects and their details\n"
                       "- Team members and their affiliations\n"
                       "- Datasets and their URLs\n"
                       "- Research methods and experiment settings\n"
                       "- Human subjects information\n\n"
                       "How can I help you today?"
        },
    ]


# Submit handler
def handle_submit(message):
    """Handle user message submission."""
    with st.spinner('Thinking...'):
        # Call the agent
        response = generate_response(message)
        write_message('assistant', response)


# Display messages in Session State
for message in st.session_state.messages:
    write_message(message['role'], message['content'], save=False)

# Handle any user input
if question := st.chat_input("Ask me about research projects..."):
    # Display user message in chat message container
    write_message('user', question)

    # Generate a response
    handle_submit(question)
