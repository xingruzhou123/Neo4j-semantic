# Please put all your Neo4j and SambaNova credentials here.

# !!!IMPORTANT!!! Make sure what local instance of Neo4j you are using has had the dbms.security.procedures lines in the config file updated with these lines. Also make sure they are uncommented and APOC is installed.

# dbms.security.procedures.unrestricted=apoc.*

# dbms.security.procedures.allowlist=apoc.*

NEO4J_URI = "neo4j-URI"
NEO4J_AUTH = ("database-name", "password")

EMBEDDING_URL = "url-for-embedding-model"
EMBEDDING_MODEL = "model-name-for-embedding-model"
EMBEDDING_API_KEY = "api-key-for-embedding-model"

CHATBOT_URL = "url-for-chatbot-model"
CHATBOT_MODEL = 'model-name-for-chatbot-model'
CHATBOT_API_KEY = "api-key-for-chatbot-model"

#Default value provided. May be between 0-1
TEMP = .1 
TOP_P = .1 
