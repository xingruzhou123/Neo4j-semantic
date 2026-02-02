"""
Vector search tool for semantic search in Neo4j.
Uses OpenAI embeddings for similarity search.

Note: This requires vector indexes to be set up in Neo4j.
Uncomment and configure the appropriate section based on your setup.
"""

import sys
sys.path.append('..')

from llm import llm, embeddings
from graph import graph
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain

# Placeholder for vector search - will be configured when embeddings are set up in Neo4j
# from langchain_neo4j import Neo4jVector

"""
Uncomment and configure this section once vector indexes are created in Neo4j:

neo4jvector = Neo4jVector.from_existing_index(
    embeddings,
    graph=graph,
    index_name="researchProjectDescription",
    node_label="ResearchProject",
    text_node_property="data_description",
    embedding_node_property="descriptionEmbedding",
    retrieval_query='''
RETURN
    node.data_description AS text,
    score,
    {
        title: node.research_project_title,
        keywords: node.keywords,
        team_members: node.team_members
    } AS metadata
'''
)

retriever = neo4jvector.as_retriever()
"""

# Create the prompt for description search
instructions = (
    "Use the given context to answer the question about research projects and datasets."
    "If you don't know the answer, say you don't know."
    "Context: {context}"
)

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", instructions),
        ("human", "{input}"),
    ]
)

# Placeholder function - returns a message when vector search is not configured
def get_description(input):
    """
    Search for research projects by description.
    Note: Vector search requires Neo4j vector indexes to be set up.
    """
    return {
        "answer": "Vector search is not yet configured. Please use the Cypher query tool for database searches, or set up vector indexes in Neo4j to enable semantic search."
    }


# Uncomment this once vector indexes are configured:
# question_answer_chain = create_stuff_documents_chain(llm, prompt)
# description_retriever = create_retrieval_chain(retriever, question_answer_chain)
#
# def get_description(input):
#     return description_retriever.invoke({"input": input})
