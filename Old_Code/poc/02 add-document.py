import os

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tqdm import tqdm

service_endpoint = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
key = os.environ["AZURE_SEARCH_API_KEY"]
report_name = "SOC.01 - ADP Autopay"


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
    soc_extract_path = os.path.join("data", "extracts", f"{report_name}.txt")

    # Load example document
    with open(soc_extract_path) as f:
        state_of_the_union = f.read()

    text_splitter = RecursiveCharacterTextSplitter(
        # Set a really small chunk size, just to show.
        chunk_size=500,
        chunk_overlap=100,
        length_function=len,
        is_separator_regex=False,
    )
    texts = text_splitter.create_documents([state_of_the_union])

    docs = []

    for index, item in tqdm(enumerate(texts)):
        chunk_id = f"{index + 1}"
        parent_doc = report_name
        chunk = item.page_content
        chunk_vector = get_embeddings(item.page_content)

        item_dict = {
            "chunkId": chunk_id,
            "parentDoc": parent_doc,
            "chunk": chunk,
            "chunkVector": chunk_vector,
        }

        docs.append(item_dict)

    return docs


if __name__ == "__main__":
    credential = AzureKeyCredential(key)
    client = SearchClient(service_endpoint, index_name, credential)
    documents = get_documents()
    client.upload_documents(documents=documents)
