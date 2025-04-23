import html
from abc import ABC
import re
from typing import IO, AsyncGenerator, List, Union
from azure.ai.formrecognizer import DocumentTable
from azure.ai.formrecognizer.aio import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential
from pypdf import PdfReader
from azure.ai.formrecognizer import DocumentLine
from core.utils import remove_whitespace
from prepdocslib.extract_toc_from_pdf import PDFTableOfContentsExtractor

from .strategy import USER_AGENT
class Page:
    """
    A single page from a pdf

    Attributes:
        page_num (int): Page number
        offset (int): If the text of the entire PDF was concatenated into a single string, the index of the first character on the page. For example, if page 1 had the text "hello" and page 2 had the text "world", the offset of page 2 is 5 ("hellow")
        text (str): The text of the page
    """

    def __init__(self, page_num: int, offset: int, text: str,pdf_page_num:int,section=''):
        self.page_num = page_num
        self.offset = offset
        self.text = text
        # self.bounding_box = bounding_box
        self.pdf_page_num = pdf_page_num
        self.section = section

class PdfParser(ABC):
    """
    Abstract parser that parses PDFs into pages
    """

    async def parse(self, content: IO) -> AsyncGenerator[Page, None]:
        if False:
            yield


class DocumentAnalysisPdfParser(PdfParser):
    """
    Concrete parser backed by Azure AI Document Intelligence that can parse PDFS into pages
    To learn more, please visit https://learn.microsoft.com/azure/ai-services/document-intelligence/overview
    """

    def __init__(
        self,
        endpoint: str,
        credential: Union[AsyncTokenCredential, AzureKeyCredential],
        model_id="prebuilt-layout",
        verbose: bool = False,
    ):
        self.model_id = model_id
        self.endpoint = endpoint
        self.credential = credential
        self.verbose = verbose
    def is_section_header_foraltText(self,text,lines:List[DocumentLine]):
        index = 0
        for line in lines:
            if index >= 5:
                return False
            if text.lower() in line.content.lower():
                position = line.content.lower().index(text.lower())
                if position <= 5:
                    return True
            index += 1
        return False
    
    def is_section_header(self,text,lines:List[DocumentLine]):
        if len(lines) <= 10:
            return True
        else:
            words_in_text = text.split(' ')
            line_no = 0
            position = None
            for line in lines:
                for word in words_in_text:
                    if word.lower() in line.content.lower():
                        position = line.content.lower().index(word.lower())
                        break
                if position is not None:
                    break
                line_no += 1
            if line_no <= 5:
                if position <= 2:
                    return True
                else:
                    return False
            elif position <= 2:
                return True
            else:
                return False
    async def parse(self, content: IO) -> AsyncGenerator[Page, None]:
        if self.verbose:
            print(f"Extracting text from '{content.name}' using Azure Document Intelligence")
            print('Endpoint ',self.endpoint)
        async with DocumentAnalysisClient(
            endpoint=self.endpoint, credential=self.credential, headers={"x-ms-useragent": USER_AGENT}
        ) as form_recognizer_client:
            poller = await form_recognizer_client.begin_analyze_document(model_id=self.model_id, document=content)
            form_recognizer_results = await poller.result()
            print(type(form_recognizer_results))
            handle_section = False
            sections = []
            try:
                paragraphs = form_recognizer_results.paragraphs
                toc_parser = PDFTableOfContentsExtractor()
                [indexPageNo,sections] = toc_parser.extract_toc_fromparagraph(paragraphs)
                if len(sections) == 4 or len(sections) == 5:
                    handle_section = True

            except Exception as e:
                print('Error in filtering paragraphs')
            print('...form_recognizer_results',len(form_recognizer_results.pages))
            
            offset = 0
            section_index = 0
            section_length = len(sections)
            section_name = 'Section 0'
            sectionsFound = []
            sectionMainTitles = ['section i', 'section ii', 'section iii', 'section iv', 'section v']  
            for page_num, page in enumerate(form_recognizer_results.pages):
                tables_on_page = [
                    table
                    for table in (form_recognizer_results.tables or [])
                    if table.bounding_regions and table.bounding_regions[0].page_number == page_num + 1
                ]

                # mark all positions of the table spans in the page
                page_offset = page.spans[0].offset
                page_length = page.spans[0].length
                table_chars = [-1] * page_length
                # bounding_boxes = []
                # for word in page.words:
                #     data = {
                #             "text": word.content,
                #             "bounding_box": word.polygon,
                #             "page_number": page.page_number
                #     }
                #     bounding_boxes.append(data)

                for table_id, table in enumerate(tables_on_page):
                    for span in table.spans:
                        # replace all table spans with "table_id" in table_chars array
                        for i in range(span.length):
                            idx = span.offset - page_offset + i
                            if idx >= 0 and idx < page_length:
                                table_chars[idx] = table_id

                # build page text by replacing characters in table spans with table html
                page_text = ""
                added_tables = set()
                for idx, table_id in enumerate(table_chars):
                    if table_id == -1:
                        page_text += form_recognizer_results.content[page_offset + idx]
                    elif table_id not in added_tables:
                        page_text += DocumentAnalysisPdfParser.table_to_html(tables_on_page[table_id])
                        added_tables.add(table_id)
                if(handle_section and page.page_number != indexPageNo):
                    matching_string = None
                    main_text = remove_whitespace(page_text)
                    for string in sections:
                        a = remove_whitespace(string)
                        if a.lower() in main_text.lower():
                            is_section_header = self.is_section_header(string,page.lines)
                            if is_section_header:
                                matching_string = string
                                sections.remove(string)
                                if sectionMainTitles:
                                    sectionMainTitles.pop(0)
                                break
                        else:
                            for title in sectionMainTitles:
                                if title.lower() in string.lower():
                                    if title.lower() in page_text.lower():
                                        is_section_header = self.is_section_header_foraltText(title.lower(),page.lines)
                                        if is_section_header:
                                            matching_string = string
                                            sections.remove(string)
                                            if sectionMainTitles:
                                                sectionMainTitles.pop(0)
                                            break
                            if matching_string is not None:
                                break
                            if matching_string is None:
                                pattern = re.compile(r"^(X|=|IX|IV|V?I{0,3}|1?0|[1-9])\s")
                                updated_title = pattern.sub('', string)
                                if updated_title in page_text:
                                    matching_string = string
                                    sections.remove(string)
                                    if sectionMainTitles:
                                        sectionMainTitles.pop(0)
                                    break
                            
                    if matching_string and page.page_number != indexPageNo:
                        if matching_string not in sectionsFound:
                            section_index += 1
                            sectionsFound.append(matching_string)
                            if section_index <= section_length:
                                section_name = 'Section ' + str(section_index)

                yield Page(page_num=page_num, offset=offset, text=page_text,pdf_page_num=page.page_number,section=section_name)
                offset += len(page_text)

    @classmethod
    def table_to_html(cls, table: DocumentTable):
        table_html = "<table>"
        rows = [
            sorted([cell for cell in table.cells if cell.row_index == i], key=lambda cell: cell.column_index)
            for i in range(table.row_count)
        ]
        for row_cells in rows:
            table_html += "<tr>"
            for cell in row_cells:
                tag = "th" if (cell.kind == "columnHeader" or cell.kind == "rowHeader") else "td"
                cell_spans = ""
                if cell.column_span is not None and cell.column_span > 1:
                    cell_spans += f" colSpan={cell.column_span}"
                if cell.row_span is not None and cell.row_span > 1:
                    cell_spans += f" rowSpan={cell.row_span}"
                table_html += f"<{tag}{cell_spans}>{html.escape(cell.content)}</{tag}>"
            table_html += "</tr>"
        table_html += "</table>"
        return table_html
