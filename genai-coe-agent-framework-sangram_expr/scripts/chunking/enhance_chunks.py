import os
import json

from tqdm import tqdm

endpoint = os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"]
credential = os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"]
openai_chatgpt_model = os.environ["AZURE_OPENAI_CHAT_MODEL"]
openai_temprature = 0.3
openai_max_tokens = 4000
report_name = os.environ["REPORT_NAME"]


def get_enhancement(text: str):
    # There are a few ways to get embeddings. This is just one example.
    import openai

    open_ai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    open_ai_key = os.getenv("AZURE_OPENAI_API_KEY")

    client = openai.AzureOpenAI(
        azure_endpoint=open_ai_endpoint,
        api_key=open_ai_key,
        api_version="2024-02-01",
    )

    prompt = """
        For the given document perform the following actions.
        1. Generate a concise summary.
        2. Extract relevant topics.
        3. Come up with a question that has a high possibility to retrieve this document.
        For each document, provide the following information in a JSON format:

        - Summary: The summary of the document.
        - Topics: Comma separated list of topics.
        - Questions: Comma separated list of questions.

        Ensure that the response is formatted as a valid JSON array of objects adhering to the RFC8259 specification.
        Return only a json object and no other descriptions about the json object or it's structrure. Don't include json keyword before the output.
        Here is the structure to follow:

        {
            "Summary": "",
            "Topics": "",
            "Questions": ""
        }
    """

    messages = [
        {"role": "user", "content": f"Here's a document {text} \n" + prompt},
    ]

    response = client.chat.completions.create(
        model=openai_chatgpt_model,
        messages=messages,
        temperature=openai_temprature,
        max_tokens=openai_max_tokens,
    )

    return response


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
            enhancement = get_enhancement(chunk["content"])
            enhancement = json.loads(enhancement.choices[0].message.content)
            item_dict = {
                "id": chunk["id"],
                "content": chunk["content"] if chunk["content"] else "empty page",
                "summary": enhancement["Summary"],
                "topics": enhancement["Topics"],
                "questions": enhancement["Questions"],
                "category": chunk["category"],
                "section": chunk["section"],
                "sourcepage": chunk["sourcepage"],
                "sourcefile": chunk["sourcefile"],
                "pdf_page_num": chunk["pdf_page_num"],
            }

            documents.append(item_dict)

    return documents


if __name__ == "__main__":
    # Construct the output folders
    chunks_folder = os.path.join("data", "enhanced-chunks")

    # Ensure the output foldesr exist
    os.makedirs(chunks_folder, exist_ok=True)

    documents = get_documents()

    file_name = f"{report_name}-chunks-enhanced.txt"
    file_path = os.path.join(chunks_folder, file_name)

    with open(file_path, "w", encoding="utf-8") as output:
        output.write(json.dumps(documents, indent=4))
