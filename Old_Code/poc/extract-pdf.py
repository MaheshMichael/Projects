import os

from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient

endpoint = os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"]
credential = os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"]

document_analysis_client = DocumentAnalysisClient(
    endpoint, AzureKeyCredential(credential)
)

soc_report_path = os.path.join("data", "documents", "SOC.01 - ADP Autopay.pdf")

with open(soc_report_path, "rb") as f:
    poller = document_analysis_client.begin_analyze_document(
        "prebuilt-layout", document=f
    )

result = poller.result()

lines = []

for page in result.pages:
    for line in page.lines:
        lines.append(line.content)

soc_extract_path = os.path.join("data", "extracts", "SOC.01 - ADP Autopay.txt")

file = open(soc_extract_path, "w", encoding="utf-8")
file.writelines(lines)
file.close()
