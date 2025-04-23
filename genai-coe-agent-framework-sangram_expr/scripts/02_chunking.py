import os
import re
import base64
import json

from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
from typing import Optional

from utils.pdfparser import DocumentAnalysisPdfParser
from utils.textsplitter import TextSplitter, SplitPage

endpoint = os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"]
credential = os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"]
report_name = os.environ["REPORT_NAME"]


class Section:
    """
    A section of a page that is stored in a search service. These sections are used as context by Azure OpenAI service
    """

    def __init__(
        self,
        split_page: SplitPage,
        content: str,
        pdf_page_no: int,
        section: str,
        category: Optional[str] = None,
    ):
        self.split_page = split_page
        self.content = content
        self.category = category
        self.pdf_page_no = pdf_page_no
        self.section = section

def create_documents(result, pdf_file):

    pdf_parser = DocumentAnalysisPdfParser(endpoint=endpoint, credential=credential)
    text_splitter = TextSplitter(has_image_embeddings=False)

    pages = [page for page in pdf_parser.parse(result=result)]

    sections = [
        Section(
            split_page=split_page,
            content=pdf_file,
            category=None,
            pdf_page_no=split_page.pdf_page_num,
            section=split_page.section,
        )
        for split_page in text_splitter.split_pages(pages)
    ]

    MAX_BATCH_SIZE = 1000
    section_batches = [
        sections[i : i + MAX_BATCH_SIZE]
        for i in range(0, len(sections), MAX_BATCH_SIZE)
    ]

    for batch_index, batch in enumerate(section_batches):
        documents = [
            {
                "id": f"file-{re.sub("[^0-9a-zA-Z_-]", "_", report_name)}-{base64.b16encode(report_name.encode("utf-8")).decode("ascii")}-page-{section_index + batch_index * MAX_BATCH_SIZE}",
                "content": section.split_page.text,
                "category": section.category,
                "section": section.section,
                "sourcepage": f"{report_name}#page={section.split_page.page_num+1}",
                "sourcefile": f"{report_name}",
                "pdf_page_num": section.split_page.pdf_page_num,
            }
            for section_index, section in enumerate(batch)
        ]

    return documents


if __name__ == "__main__":
    # Construct the output folders
    chunks_folder = os.path.join("data", "chunks")

    # Ensure the output foldesr exist
    os.makedirs(chunks_folder, exist_ok=True)

    document_analysis_client = DocumentAnalysisClient(
        endpoint, AzureKeyCredential(credential)
    )

    soc_report_path = os.path.join("data", "document", f"{report_name}.pdf")

    with open(soc_report_path, "rb") as pdf_file:
        poller = document_analysis_client.begin_analyze_document(
            "prebuilt-layout", document=pdf_file
        )

        result = poller.result()

        documents = create_documents(result, pdf_file)

    file_name = f"{report_name}-chunks.txt"
    file_path = os.path.join(chunks_folder, file_name)

    with open(file_path, "w", encoding="utf-8") as output:
        output.write(json.dumps(documents, indent=4))