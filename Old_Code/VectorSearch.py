import os
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
import openai

user_query = "Payroll Summary"

def search_similar_documents(user_query: str):
    """
    Get embeddings for the user query and search for similar documents in Azure Search.

    Args:
        user_query (str): The input import os
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient

# Initialize the Document Analysis client using Azure credentials
endpoint = os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"]
credential = os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"]
client = DocumentAnalysisClient(endpoint, AzureKeyCredential(credential))

# Path to the PDF document to be analyzed
soc_report_path = os.path.join("data", "documents", "SOC.01 - ADP Autopay.pdf")

# Open the PDF document and analyze it
with open(soc_report_path, "rb") as f:
    # Start the document analysis process using the prebuilt layout model
    poller = client.begin_analyze_document("prebuilt-layout", document=f)
    # Wait for the analysis to complete and get the result
    result = poller.result()

# Extract lines of text from the analysis result
lines = [line.content for page in result.pages for line in page.lines]

# Print the extracted lines to the console
print("\n".join(lines))

# Define the path for saving the extracted text to a file
soc_extract_path = os.path.join("data", "extracts", "SOC.01 - ADP Autopay.txt")

# Save the extracted lines to a text file
with open(soc_extract_path, "w", encoding="utf-8") as file:
    file.writelines(lines)

# Print a confirmation message indicating where the output has been saved
print(f"\nSample output saved to {soc_extract_path}")query to search for similar documents.

    Returns:
        None: Prints the search results directly.
    """
    # Load Azure Search service configuration from environment variables
    service_endpoint = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
    index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
    key = os.environ["AZURE_SEARCH_API_KEY"]
    k_nearest_neighbors = 3  # Number of nearest neighbors to retrieve

    # Load OpenAI configuration from environment variables
    open_ai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    open_ai_key = os.getenv("AZURE_OPENAI_API_KEY")

    # Initialize OpenAI client
    openai_client = openai.AzureOpenAI(
        azure_endpoint=open_ai_endpoint,
        api_key=open_ai_key,
        api_version="2023-03-15-preview",
    )

    # Get embeddings for the user query
    embedding = openai_client.embeddings.create(input=[user_query], model="text-embedding-ada-002")
    query_vector = embedding.data[0].embedding

    # Initialize the Azure Search client
    search_client = SearchClient(service_endpoint, index_name, AzureKeyCredential(key))

    # Create a vectorized query
    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=k_nearest_neighbors,
        fields="chunkVector",
    )

    # Execute the hybrid search
    results = search_client.search(
        search_text=user_query,
        vector_queries=[vector_query],
        select=["chunkId", "parentDoc", "chunk"],
    )

    # Print the results
    print("Search Results:")
    for result in results:
        print(f"Chunk ID: {result['chunkId']}, Parent Document: {result['parentDoc']}, Chunk: {result['chunk']}")