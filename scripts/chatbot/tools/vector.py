"""
Vector search tool for semantic search over ingested report chunks in Neo4j.
Requires DocumentChunk nodes and the 'documentChunkIndex' vector index
(created by ingest_reports.py).
"""

import sys
sys.path.append('..')

from llm import llm, embeddings
from graph import graph
from langchain_core.prompts import ChatPromptTemplate
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.chains import create_retrieval_chain
from langchain_neo4j import Neo4jVector, Neo4jGraph
import config

# If graph is None (APOC unavailable), create a minimal Neo4jGraph for vector search
_graph = graph
if _graph is None:
    _graph = Neo4jGraph(
        url=config.NEO4J_URI,
        username=config.NEO4J_USERNAME,
        password=config.NEO4J_PASSWORD,
        refresh_schema=False,
    )

neo4jvector = Neo4jVector.from_existing_index(
    embeddings,
    graph=_graph,
    index_name="documentChunkIndex",
    node_label="DocumentChunk",
    text_node_property="text",
    embedding_node_property="embedding",
    retrieval_query="""
MATCH (pr:ProjectReports)-[:CONTAINS_CHUNK]->(node)
MATCH (rp:ResearchProject)-[:HAS_REPORTS]->(pr)
RETURN node.text AS text, score,
  { source_file: node.source_file, project_title: rp.research_project_title } AS metadata
"""
)

retriever = neo4jvector.as_retriever()

instructions = (
    "Use the given context from dataset reports to answer the question. "
    "If you don't know the answer, say you don't know."
    "Context: {context}"
)

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", instructions),
        ("human", "{input}"),
    ]
)

question_answer_chain = create_stuff_documents_chain(llm, prompt)
description_retriever = create_retrieval_chain(retriever, question_answer_chain)


def search_reports(input):
    return description_retriever.invoke({"input": input})
