from neo4j import GraphDatabase

# Neo4j connection settings
URI = "bolt://localhost:7687"
USERNAME = "neo4j"
PASSWORD = "12345678"

def create_test_node(driver):
    """Create a test node in the database."""
    with driver.session() as session:
        result = session.run(
            "CREATE (n:TestNode {name: $name, created: datetime()}) RETURN n",
            name="Hello from TACC"
        )
        record = result.single()
        node = record["n"]
        print(f"Created test node: {node}")
        return node

def main():
    # Connect to Neo4j
    driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))

    try:
        # Verify connectivity
        driver.verify_connectivity()
        print("Successfully connected to Neo4j!")

        # Create a test node
        create_test_node(driver)
        print("Test node created successfully!")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.close()

if __name__ == "__main__":
    main()
