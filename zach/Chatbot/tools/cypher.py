import streamlit as st
from llm import llm
from graph import graph
from langchain.prompts.prompt import PromptTemplate


CYPHER_GENERATION_TEMPLATE = """
You are an expert Neo4j Developer translating user questions into Cypher to answer questions about porous media.
Convert the user's question based on the schema.

Use only the provided relationship types and properties in the schema.
Do not use any other relationship types or properties that are not provided.

Do not return entire nodes or embedding properties.

Fine Tuning:

Sometimes relevant keywords may be contained in the description instead of simply in the title.
Avoid using the UNION or UNION ALL operator unless absolutely necessary. Prefer combining conditions within a single MATCH or WHERE clause using logical operators like OR.

People may use the words "projects" and "datasets" interchangably.

If you do use it, you MUST make sure it follows a format like this where all return fields have the same column names.
MATCH (a:TypeA)
WHERE <conditions>
RETURN a.prop1 AS field1, a.prop2 AS field2

UNION

MATCH (b:TypeB)
WHERE <conditions>
RETURN b.prop1 AS field1, b.prop2 AS field2

Schema:
{schema}

Question:
{question}

Cypher Query:
"""

cypher_prompt = PromptTemplate.from_template(CYPHER_GENERATION_TEMPLATE)

# Create the Cypher QA chain
from langchain_neo4j import GraphCypherQAChain

cypher_qa = GraphCypherQAChain.from_llm(
    llm,
    graph=graph,
    verbose=True,
    cypher_prompt=cypher_prompt,
    allow_dangerous_requests=True,
    return_intermediate_steps=True,
    top_k=10,
    # return_direct = True,
)
