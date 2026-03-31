"""
LLM and Embeddings setup using OpenAI API.
"""

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import config

# Initialize the OpenAI LLM
llm = ChatOpenAI(
    model=config.OPENAI_MODEL,
    api_key=config.OPENAI_API_KEY,
    base_url=config.OPENAI_BASE_URL,
    temperature=config.TEMPERATURE
)

# Initialize OpenAI Embeddings
embeddings = OpenAIEmbeddings(
    model=config.OPENAI_EMBEDDING_MODEL,
    base_url=config.OPENAI_BASE_URL,
    api_key=config.OPENAI_API_KEY,
    check_embedding_ctx_length=False,
)
