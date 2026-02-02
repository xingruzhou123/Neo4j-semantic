"""
Script to delete all nodes and relationships in the Neo4j database.
"""

from neo4j import GraphDatabase

# Neo4j connection settings
URI = "bolt://localhost:7687"
USERNAME = "neo4j"
PASSWORD = "12345678"


def delete_all_nodes(driver):
    """Delete all nodes and relationships in the database."""
    with driver.session() as session:
        # Get count before deletion
        result = session.run("MATCH (n) RETURN count(n) as count")
        count_before = result.single()["count"]

        # Delete all nodes and relationships
        session.run("MATCH (n) DETACH DELETE n")

        # Verify deletion
        result = session.run("MATCH (n) RETURN count(n) as count")
        count_after = result.single()["count"]

        print(f"Deleted {count_before} nodes. Remaining: {count_after}")


def main():
    driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))

    try:
        driver.verify_connectivity()
        print("Connected to Neo4j successfully!")

        delete_all_nodes(driver)
        print("All nodes deleted successfully!")

    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        driver.close()


if __name__ == "__main__":
    main()
