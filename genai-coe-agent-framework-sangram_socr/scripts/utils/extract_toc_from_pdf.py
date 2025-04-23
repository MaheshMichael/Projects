import re
from typing import List
from azure.ai.formrecognizer import DocumentTable, DocumentPage, DocumentParagraph
from enum import Enum


class IndexPageType(Enum):
    WITHSECTIONTEXTTYPE = 1
    WITHSECTIONNUMBER = (2,)
    WITHSECTIONNUMBERROMAN = (3,)
    WITHPLAINTEXT = (4,)
    NONE = 5


roman_chars = [
    "I ",
    "II ",
    "III ",
    "IV ",
    "V ",
    "= ",
    "I:",
    "II:",
    "III:",
    "IV:",
    "V:",
    "=:",
]
roman_pattern = r"^(M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3}))"


class PDFTableOfContentsExtractor:
    def __init__(self):
        pass

    def starts_with_roman_letter(self, string):
        return any(item in string for item in roman_chars)

    def extract_toc(self, paragraphs: List[DocumentPage]) -> List[str]:
        toc = []
        for paragraph in paragraphs:
            if self.is_toc_entry(paragraph):
                toc.append(self.create_section(paragraph))
        return toc

    def handleIndexPageType(self, indexPageType, values):
        # handle the index page type sample text SECTION ONE PAGE Independent Service Auditor’s Report provided by Ernst & Young   \
        # Independent Service Auditor’s Report ............................................................................................ 4
        titles = []
        if indexPageType == indexPageType.WITHSECTIONTEXTTYPE:
            titles = [value for value in values if "section" in value.lower()]

        elif indexPageType == indexPageType.WITHSECTIONNUMBERROMAN:
            for s in values:
                if self.starts_with_roman_letter(s):
                    titles.append(s)
                if s.startswith("V") and len(titles) < 5:
                    titles = []
                    break

        elif indexPageType == indexPageType.WITHSECTIONNUMBER:
            titles = [value for value in values if value[0].isdigit()]
        elif indexPageType == indexPageType.WITHPLAINTEXT:
            titles = [value for value in values if not value.isdigit()]
        if len(titles) > 0:
            # trim leading and traling spaces
            titles = [value.strip() for value in titles]
            # trin page number
            titles = [value.split("PAGE", 1)[0].strip() for value in titles]
            titles = [
                value
                for value in titles
                if "table of contents" not in value.lower()
                and "contents" not in value.lower()
                and "table of content" not in value.lower()
                and "content" not in value.lower()
            ]
            titles = [
                value.rstrip() if value[-1].isspace() and value[-2].isdigit() else value
                for value in titles
            ]
            titles = [value for value in titles if not value.isdigit()]
            titles = [re.sub(r"\d+$", "", value) for value in titles if value]
            titles = [value.strip() for value in titles]
            titles = [
                value[:-1] if value[-1] == "." else value for value in titles if value
            ]
            return titles
        return []

    def find_page_number(self, pages: List[DocumentPage]):
        pass

    def extract_toc_fromparagraph(
        self, paragraphs: List[DocumentParagraph]
    ) -> List[str]:
        paragraph = [
            paragraph
            for paragraph in paragraphs
            if any(
                keyword.lower() in paragraph.content.lower()
                for keyword in ["table of contents", "contents"]
            )
        ]
        if paragraph and len(paragraph) > 0:
            bounding_region = paragraph[0].bounding_regions[0]
            pageNo = bounding_region.page_number
            sectiontitles = [
                paragraph
                for paragraph in paragraphs
                if paragraph.bounding_regions[0].page_number == pageNo
            ]
            values = [sectiontitle.content for sectiontitle in sectiontitles]
            indexPageType = IndexPageType.NONE
            if len(values) > 0:
                match = []
                for s in values:
                    if self.starts_with_roman_letter(s):
                        match.append(s)
                if any(value for value in values if "section" in value.lower()):
                    indexPageType = indexPageType.WITHSECTIONTEXTTYPE
                elif len(match) > 0:
                    indexPageType = indexPageType.WITHSECTIONNUMBERROMAN
                elif any(value[0].isdigit() for value in values):
                    data = [value for value in values if value[0].isdigit()]
                    if any(not value.isdigit() for value in data):
                        indexPageType = indexPageType.WITHSECTIONNUMBER
                    else:
                        indexPageType = indexPageType.WITHPLAINTEXT
                sectionTitles = self.handleIndexPageType(indexPageType, values)
                return pageNo, sectionTitles
        return []
