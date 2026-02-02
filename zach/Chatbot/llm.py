import streamlit as st
from langchain_sambanova import ChatSambaStudio
from langchain_sambanova import SambaStudioEmbeddings
import passwords

embedding_model = passwords.EMBEDDING_MODEL
embedding_url = passwords.EMBEDDING_URL
embedding_api_key = passwords.EMBEDDING_API_KEY

chatbot_model = passwords.CHATBOT_MODEL
chatbot_url = passwords.CHATBOT_URL
chatbot_api_key = passwords.CHATBOT_API_KEY

llm = ChatSambaStudio(model=chatbot_model, sambastudio_url=chatbot_url,sambastudio_api_key=chatbot_api_key,temperature=0.7)

embeddings = SambaStudioEmbeddings(model=embedding_model,sambastudio_api_key=embedding_api_key, sambastudio_url=embedding_url)