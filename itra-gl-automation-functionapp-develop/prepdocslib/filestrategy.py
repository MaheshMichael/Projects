from enum import Enum
from typing import List, Optional

from .embeddings import ImageEmbeddings, OpenAIEmbeddings
from .listfilestrategy import File, ListFileStrategy
from .pdfparser import PdfParser
from .searchmanager import SearchManager, Section
from .strategy import SearchInfo, Strategy
from .textsplitter import TextSplitter
import fitz


class DocumentAction(Enum):
    Add = 0
    Remove = 1
    RemoveAll = 2


class FileStrategy(Strategy):
    """
    Strategy for ingesting documents into a search service from files stored either locally or in a data lake storage account
    """

    def __init__(
        self,
        list_file_strategy: ListFileStrategy,
        pdf_parser: PdfParser,
        text_splitter: TextSplitter,
        document_action: DocumentAction = DocumentAction.Add,
        embeddings: Optional[OpenAIEmbeddings] = None,
        image_embeddings: Optional[ImageEmbeddings] = None,
        search_analyzer_name: Optional[str] = None,
        use_acls: bool = False,
        category: Optional[str] = None,
        file:File = None
    ):
        self.list_file_strategy = list_file_strategy
        self.pdf_parser = pdf_parser
        self.text_splitter = text_splitter
        self.document_action = document_action
        self.embeddings = embeddings
        self.image_embeddings = image_embeddings
        self.search_analyzer_name = search_analyzer_name
        self.use_acls = use_acls
        self.category = category
        self.file = file
    async def setup(self, search_info: SearchInfo):
        search_manager = SearchManager(
            search_info,
            self.search_analyzer_name,
            self.use_acls,
            self.embeddings,
            search_images=self.image_embeddings is not None,
        )
        await search_manager.create_index()

    async def run(self, search_info: SearchInfo):
        search_manager = SearchManager(search_info, self.search_analyzer_name, self.use_acls, self.embeddings)
        if self.document_action == DocumentAction.Add:
            try:
               pages = [page async for page in self.pdf_parser.parse(content=self.file.content)]
               if search_info.verbose:
                print(f"Splitting '{self.file.filename()}' into sections")
                sections = [
                        Section(split_page, content=self.file, category=self.category,pdf_page_no=split_page.pdf_page_num,section=split_page.section)
                        for split_page in self.text_splitter.split_pages(pages)
                    ]
                print('** sections ',len(sections))
                await search_manager.update_content(sections, None)
                return True
            except Exception as e:
                return False
            
                # if self.file:
                #     self.file.close()