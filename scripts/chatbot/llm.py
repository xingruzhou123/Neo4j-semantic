"""
LLM and Embeddings setup using OpenAI API.
"""

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import config

# Initialize the OpenAI LLM
llm = ChatOpenAI(
    model=config.OPENAI_MODEL,
    api_key=config.OPENAI_API_KEY,
    temperature=config.TEMPERATURE
)

# Initialize OpenAI Embeddings
embeddings = OpenAIEmbeddings(
    model=config.OPENAI_EMBEDDING_MODEL,
    api_key=config.OPENAI_API_KEY
)
