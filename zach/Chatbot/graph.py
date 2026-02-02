import streamlit as st
from langchain_neo4j import Neo4jGraph
import passwords

graph = Neo4jGraph(
    url=passwords.NEO4J_URI,
    username=passwords.NEO4J_AUTH[0],
    password=passwords.NEO4J_AUTH[1],
)