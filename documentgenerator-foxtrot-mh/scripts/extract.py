import os
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from dotenv import load_dotenv

load_dotenv()

user_document = os.getenv("USER_DOCUMENT")

endpoint = os.getenv("DOCUMENTINTELLIGENCE_ENDPOINT")
credential = AzureKeyCredential(os.getenv("DOCUMENTINTELLIGENCE_API_KEY"))
document_intelligence_client = DocumentIntelligenceClient(endpoint, credential)

user_document_path = os.path.join("data", "documents", user_document)

with open(user_document_path, "rb") as f:
    poller = document_intelligence_client.begin_analyze_document(
        "prebuilt-layout", body=f
    )
result: AnalyzeResult = poller.result()

output_path = os.path.join("data", "intermediate", "out.txt")

with open(output_path, "w", encoding="utf-8") as f:
    f.write(str(result.pages))
