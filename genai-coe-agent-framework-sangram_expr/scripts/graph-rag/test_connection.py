import os
from neo4j import GraphDatabase

neo4j_username = os.environ["NEO4J_USERNAME"]
neo4j_password = os.environ["NEO4J_PASSWORD"]
neo4j_connection_uri = os.environ["NEO4J_CONNECTION_URI"]

# URI examples: "neo4j://localhost", "neo4j+s://xxx.databases.neo4j.io"
URI = neo4j_connection_uri
AUTH = (neo4j_username, neo4j_password)

with GraphDatabase.driver(URI, auth=AUTH) as driver:
    driver.verify_connectivity()
