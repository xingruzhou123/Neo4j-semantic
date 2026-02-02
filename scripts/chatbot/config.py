"""
Configuration file for the chatbot.
Reads API keys from environment variables or .env file.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Neo4j connection settings
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "12345678"

# OpenAI settings (reads from .env file or environment variable)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Check if API key is set
if not OPENAI_API_KEY:
    print("WARNING: OPENAI_API_KEY is not set!")
    print("Please add it to .env file or run: export OPENAI_API_KEY='your-key-here'")

OPENAI_MODEL = "gpt-4o-mini"  # Can use "gpt-4o" or "gpt-3.5-turbo" as well
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"

# LLM parameters
TEMPERATURE = 0.7
