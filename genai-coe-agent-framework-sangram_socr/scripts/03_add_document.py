import os
import json

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from tqdm import tqdm

service_endpoint = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
key = os.environ["AZURE_SEARCH_API_KEY"]
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


def get_documents():
    chunks_folder = os.path.join("data", "chunks")
    file_name = f"{report_name}-chunks.txt"
    file_path = os.path.join(chunks_folder, file_name)

    # Load documents
    with open(file_path) as chunks_file:
        chunks = json.loads(chunks_file.read())

    documents = []

    for chunk in tqdm(chunks):
        if chunk["content"]:
            item_dict = {
                "id": chunk["id"],
                "content": chunk["content"] if chunk["content"] else "empty page",
                "embedding": get_embeddings(chunk["content"]),
                "category": chunk["category"],
                "section": chunk["section"],
                "sourcepage": chunk["sourcepage"],
                "sourcefile": chunk["sourcefile"],
                "pdf_page_num": chunk["pdf_page_num"],
            }

            documents.append(item_dict)

    return documents


if __name__ == "__main__":
    credential = AzureKeyCredential(key)
    client = SearchClient(service_endpoint, index_name, credential)
    documents = get_documents()
    client.upload_documents(documents=documents)
