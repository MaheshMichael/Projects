import os
import json

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.search.documents.models import QueryType

service_endpoint = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
key = os.environ["AZURE_SEARCH_API_KEY"]
k_nearest_neighbors = 50
report_name = os.environ["REPORT_NAME"]


def get_embeddings(text: str):
    # There are a few ways to get embeddings. This is just one example.
    import openai

    open_ai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    open_ai_key = os.getenv("AZURE_OPENAI_API_KEY")

    client = openai.AzureOpenAI(
        azure_endpoint=open_ai_endpoint,
        api_key=open_ai_key,
        api_version="2023-03-15-preview",
    )
    embedding = client.embeddings.create(input=[text], model="text-embedding-ada-002")
    return embedding.data[0].embedding


def semantic_query(query):
    search_client = SearchClient(service_endpoint, index_name, AzureKeyCredential(key))
    vector_query = VectorizedQuery(
        vector=get_embeddings(query),
        k_nearest_neighbors=k_nearest_neighbors,
        fields="embedding",
    )

    results = search_client.search(
        query_type=QueryType.SEMANTIC,
        semantic_configuration_name="my-semantic-config",
        search_text=query,
        vector_queries=[vector_query],
        filter=f"sourcefile eq '{report_name}' and section eq 'Section 3'",
        select=["id", "sourcefile", "content", "pdf_page_num"],
    )

    return results


if __name__ == "__main__":
    # Construct the output folder path
    search_output_folder = os.path.join("data", "search")

    # Ensure the output folder exists
    os.makedirs(search_output_folder, exist_ok=True)

    query = (
        "sap applications in scope or sap systems in scope or sap platforms in scope"
    )
    results = semantic_query(query=query)

    file_name = f"{report_name}-search.txt"
    file_path = os.path.join(search_output_folder, file_name)

    with open(file_path, "w", encoding="utf-8") as output:
        output.write(json.dumps(list(results), indent=4))
