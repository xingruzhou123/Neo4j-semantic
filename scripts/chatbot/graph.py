"""
Neo4j Graph connection setup.
"""

from langchain_neo4j import Neo4jGraph
from neo4j import GraphDatabase
import config

# Try to create Neo4jGraph with APOC, fall back to basic driver if not available
try:
    graph = Neo4jGraph(
        url=config.NEO4J_URI,
        username=config.NEO4J_USERNAME,
        password=config.NEO4J_PASSWORD,
    )
except ValueError as e:
    if "APOC" in str(e):
        print("Warning: APOC not available. Using basic Neo4j driver.")
        # Create a basic driver for simple queries
        graph = None
        driver = GraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD)
        )
    else:
        raise e

# Basic Neo4j driver for direct queries when APOC is not available
driver = GraphDatabase.driver(
    config.NEO4J_URI,
    auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD)
)
