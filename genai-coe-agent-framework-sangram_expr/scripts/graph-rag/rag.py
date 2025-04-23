from langchain.document_loaders import TextLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain_openai import AzureChatOpenAI
from langchain_experimental.graph_transformers import LLMGraphTransformer
from llama_index.graph_stores.neo4j import Neo4jGraphStore
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.retrievers import KnowledgeGraphRAGRetriever

from llama_index.core.data_structs import Node
from llama_index.core.response_synthesizers import ResponseMode
from llama_index.core import get_response_synthesizer
import os

open_ai_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
open_ai_key = os.environ["AZURE_OPENAI_API_KEY"]
azure_deployment = os.environ["AZURE_OPENAI_CHAT_MODEL"]
api_version = os.environ["AZURE_OPENAI_API_VERSION"]
neo4j_username = os.environ["NEO4J_USERNAME"]
neo4j_password = os.environ["NEO4J_PASSWORD"]
neo4j_connection_uri = os.environ["NEO4J_CONNECTION_URI"]

# Load an example document
with open(os.path.join("scripts", "graph-rag", "data.txt")) as f:
    data = f.read()

text_splitter = CharacterTextSplitter(chunk_size=200, chunk_overlap=20)
texts = text_splitter.create_documents([data])

# Initialize LLM
llm = AzureChatOpenAI(
    azure_deployment=azure_deployment, api_version=api_version, temperature=0
)

# Extract Knowledge Graph
llm_transformer = LLMGraphTransformer(llm=llm)
graph_documents = llm_transformer.convert_to_graph_documents(texts)

# Store Knowledge Graph in Neo4j
graph_store = Neo4jGraphStore(
    url=neo4j_connection_uri, username=neo4j_username, password=neo4j_password
)
graph_store.write_graph(graph_documents)

# Retrieve Knowledge for RAG
graph_rag_retriever = KnowledgeGraphRAGRetriever(
    storage_context=graph_store.storage_context, verbose=True
)
query_engine = RetrieverQueryEngine.from_args(graph_rag_retriever)

# Retrieve Knowledge for RAG
graph_rag_retriever = KnowledgeGraphRAGRetriever(
    storage_context=graph_store.storage_context, verbose=True
)
query_engine = RetrieverQueryEngine.from_args(graph_rag_retriever)


# Initialize the ResponseSynthesizer instance
response_synthesizer = get_response_synthesizer(response_mode=ResponseMode.COMPACT)

response = response_synthesizer.synthesize(
    "query text", nodes=[Node(text="Where does Sarah work?"), ...]
)
