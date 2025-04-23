import os

from langchain_text_splitters import RecursiveCharacterTextSplitter

soc_extract_path = os.path.join("data", "extracts", "SOC.01 - ADP Autopay.txt")

# Load example document
with open(soc_extract_path) as f:
    soc_extract = f.read()

text_splitter = RecursiveCharacterTextSplitter(
    # Set a really small chunk size, just to show.
    chunk_size=500,
    chunk_overlap=100,
    length_function=len,
    is_separator_regex=False,
)
texts = text_splitter.create_documents([soc_extract])
print(len(texts))
# print(texts[0].page_content)
# print(texts[1].page_content)
