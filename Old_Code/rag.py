import os
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
print(f"\nSample output saved to {soc_extract_path}")