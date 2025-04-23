from typing import Generator, List

from .pdfparser import Page


class SplitPage:
    """
    A section of a page that has been split into a smaller chunk.
    """

    def __init__(self, page_num: int, text: str,pdf_page_num:int,section=''):
        self.page_num = page_num
        self.text = text
        self.pdf_page_num = pdf_page_num
        self.section = section



class TextSplitter:
    """
    Class that splits pages into smaller chunks. This is required because embedding models may not be able to analyze an entire page at once
    """

    def __init__(self, has_image_embeddings: bool, verbose: bool = False):
        self.sentence_endings = [".", "!", "?"]
        self.word_breaks = [",", ";", ":", " ", "(", ")", "[", "]", "{", "}", "\t", "\n"]
        self.max_section_length = 1000
        self.sentence_search_limit = 100
        self.section_overlap = 100
        self.verbose = verbose
        self.has_image_embeddings = has_image_embeddings

    def split_pages(self, pages: List[Page]) -> Generator[SplitPage, None, None]:
        # Chunking is disabled when using GPT4V. To be updated in the future.
        if 1:
            for i, page in enumerate(pages):
                yield SplitPage(page_num=i, text=page.text,pdf_page_num=page.pdf_page_num,section=page.section)
        else:
            def find_page(offset):
                num_pages = len(pages)
                for i in range(num_pages - 1):
                    if offset >= pages[i].offset and offset < pages[i + 1].offset:
                        return [pages[i].page_num,pages[i].pdf_page_num,pages[i].section]
                return [pages[num_pages - 1].page_num,pages[num_pages - 1].pdf_page_num,pages[num_pages - 1].section]

            all_text = "".join(page.text for page in pages)
            length = len(all_text)
            start = 0
            end = length
            while start + self.section_overlap < length:
                last_word = -1
                end = start + self.max_section_length

                if end > length:
                    end = length
                else:
                    # Try to find the end of the sentence
                    while (
                        end < length
                        and (end - start - self.max_section_length) < self.sentence_search_limit
                        and all_text[end] not in self.sentence_endings
                    ):
                        if all_text[end] in self.word_breaks:
                            last_word = end
                        end += 1
                    if end < length and all_text[end] not in self.sentence_endings and last_word > 0:
                        end = last_word  # Fall back to at least keeping a whole word
                if end < length:
                    end += 1

                # Try to find the start of the sentence or at least a whole word boundary
                last_word = -1
                while (
                    start > 0
                    and start > end - self.max_section_length - 2 * self.sentence_search_limit
                    and all_text[start] not in self.sentence_endings
                ):
                    if all_text[start] in self.word_breaks:
                        last_word = start
                    start -= 1
                if all_text[start] not in self.sentence_endings and last_word > 0:
                    start = last_word
                if start > 0:
                    start += 1

                section_text = all_text[start:end]
                [page_num,pdf_page_num,section]=find_page(start)
                yield SplitPage(page_num=page_num,pdf_page_num=pdf_page_num, text=section_text,section=section)

                last_table_start = section_text.rfind("<table")
                if last_table_start > 2 * self.sentence_search_limit and last_table_start > section_text.rfind("</table"):
                    # If the section ends with an unclosed table, we need to start the next section with the table.
                    # If table starts inside sentence_search_limit, we ignore it, as that will cause an infinite loop for tables longer than MAX_SECTION_LENGTH
                    # If last table starts inside section_overlap, keep overlapping
                    if self.verbose:
                        print(
                            f"Section ends with unclosed table, starting next section with the table at page {find_page(start)} offset {start} table start {last_table_start}"
                        )
                    start = min(end - self.section_overlap, start + last_table_start)
                else:
                    start = end - self.section_overlap

            if start + self.section_overlap < end:
                [page_num,pdf_page_num,section]=find_page(start)
                yield SplitPage(page_num=find_page(start),pdf_page_num=pdf_page_num,section=section, text=all_text[start:end])
