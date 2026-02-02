"""
Utility functions for the chatbot.
"""

import streamlit as st
import uuid


def write_message(role, content, save=True):
    """
    Helper function that saves a message to the session state
    and then writes a message to the UI.
    """
    # Append to session state
    if save:
        st.session_state.messages.append({"role": role, "content": content})

    # Write to UI
    with st.chat_message(role):
        st.markdown(content)


def get_session_id():
    """Get the current session ID."""
    try:
        from streamlit.runtime.scriptrunner.script_run_context import get_script_run_ctx
        ctx = get_script_run_ctx()
        if ctx:
            return ctx.session_id
    except Exception:
        pass
    # Fallback to a random UUID if not running in Streamlit
    return str(uuid.uuid4())
