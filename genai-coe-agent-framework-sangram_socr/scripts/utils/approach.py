import os
import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, List, Optional, Union, cast

from azure.search.documents import SearchClient
from azure.search.documents.models import (
    QueryCaptionResult,
    QueryType,
    VectorizedQuery,
)

from openai import AzureOpenAI

from utils.text import nonewlines

report_name = os.getenv("REPORT_NAME")

@dataclass
class Document:
    id: Optional[str]
    content: Optional[str]
    searchscore: Optional[float]
    embedding: Optional[List[float]]
    image_embedding: Optional[List[float]]
    category: Optional[str]
    sourcepage: Optional[str]
    sourcefile: Optional[str]
    oids: Optional[List[str]]
    groups: Optional[List[str]]
    captions: List[QueryCaptionResult]
    pdfpageno: Optional[str]

    def serialize_for_results(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "embedding": Document.trim_embedding(self.embedding),
            "imageEmbedding": Document.trim_embedding(self.image_embedding),
            "category": self.category,
            "sourcepage": self.sourcepage,
            "sourcefile": self.sourcefile,
            "oids": self.oids,
            "groups": self.groups,
            "pdfpageno": self.pdfpageno,
            "captions": (
                [
                    {
                        "additional_properties": caption.additional_properties,
                        "text": caption.text,
                        "highlights": caption.highlights,
                    }
                    for caption in self.captions
                ]
                if self.captions
                else []
            ),
        }

    @classmethod
    def trim_embedding(cls, embedding: Optional[List[float]]) -> Optional[str]:
        """Returns a trimmed list of floats from the vector embedding."""
        if embedding:
            if len(embedding) > 2:
                # Format the embedding list to show the first 2 items followed by the count of the remaining items."""
                return f"[{embedding[0]}, {embedding[1]} ...+{len(embedding) - 2} more]"
            else:
                return str(embedding)

        return None


@dataclass
class ThoughtStep:
    title: str
    description: Optional[Any]
    props: Optional[dict[str, Any]] = None


class Approach:
    def __init__(
        self,
        search_client: SearchClient,
        openai_client: AzureOpenAI,
        query_language: Optional[str],
        query_speller: Optional[str],
        embedding_deployment: Optional[
            str
        ],  # Not needed for non-Azure OpenAI or for retrieval_mode="text"
        embedding_model: str,
        openai_host: str,
    ):
        self.search_client = search_client
        self.openai_client = openai_client
        self.query_language = query_language
        self.query_speller = query_speller
        self.embedding_deployment = embedding_deployment
        self.embedding_model = embedding_model
        self.openai_host = openai_host

    def build_filter(
        self, overrides: dict[str, Any], auth_claims: dict[str, Any]
    ) -> Optional[str]:
        exclude_category = overrides.get("exclude_category") or None
        filters = []
        if exclude_category:
            filters.append(
                "category ne '{}'".format(exclude_category.replace("'", "''"))
            )
        # if security_filter:
        #   filters.append(security_filter)
        return None if len(filters) == 0 else " and ".join(filters)

    def search(
        self,
        top: int,
        query_text: Optional[str],
        filter: Optional[str],
        vectors: List[VectorizedQuery],
        use_semantic_ranker: bool,
        use_semantic_captions: bool,
        query_type: QueryType = QueryType.SEMANTIC,
    ) -> List[Document]:
        # Use semantic ranker if requested and if retrieval mode is text or hybrid (vectors + text)
        if use_semantic_ranker and query_text:
            results = self.search_client.search(
                query_type=query_type,
                semantic_configuration_name="my-semantic-config",
                search_text=query_text,
                vector_queries=vectors,
                filter=filter,
                # query_language=self.query_language,
                # query_speller=self.query_speller,
                top=top,
                query_caption=(
                    "extractive|highlight-false" if use_semantic_captions else None
                ),
            )
        else:
            results = self.search_client.search(
                search_text=query_text or "",
                filter=filter,
                top=top,
                vector_queries=vectors,
            )

        ################################
        #### Persist Search Results ####
        ################################

        # Construct the output folder path
        search_output_folder = os.path.join("data", "search")

        # Ensure the output folder exists
        os.makedirs(search_output_folder, exist_ok=True)

        file_name = f"{report_name}-search.txt"
        file_path = os.path.join(search_output_folder, file_name)

        with open(file_path, "w", encoding="utf-8") as output:
            output.write(json.dumps(list(results), indent=4))

        documents = []
        for page in results.by_page():
            for document in page:
                documents.append(
                    Document(
                        id=document.get("id"),
                        searchscore=document.get("@search.score"),
                        content=document.get("content"),
                        embedding=document.get("embedding"),
                        image_embedding=document.get("imageEmbedding"),
                        category=document.get("category"),
                        sourcepage=document.get("sourcepage"),
                        sourcefile=document.get("sourcefile"),
                        oids=document.get("oids"),
                        groups=document.get("groups"),
                        captions=cast(
                            List[QueryCaptionResult], document.get("@search.captions")
                        ),
                        pdfpageno=document.get("pdf_page_num"),
                    )
                )
        return documents

    def get_sources_content(
        self,
        results: List[Document],
        use_semantic_captions: bool,
        use_image_citation: bool,
    ) -> list[str]:
        if use_semantic_captions:
            return [
                (self.get_citation((doc.sourcepage or ""), use_image_citation))
                + ": "
                + (str(doc.searchscore) or " ")
                + ": "
                + nonewlines(
                    " . ".join([cast(str, c.text) for c in (doc.captions or [])])
                )
                for doc in results
            ]
        else:
            return [
                (self.get_citation((doc.sourcepage or ""), use_image_citation))
                + ": Confidence Score="
                + (str(doc.searchscore) or " ")
                + ": "
                + nonewlines(doc.content or "")
                for doc in results
            ]

    def get_citation(self, sourcepage: str, use_image_citation: bool) -> str:
        if use_image_citation:
            return sourcepage
        else:
            path, ext = os.path.splitext(sourcepage)
            if ext.lower() == ".png":
                page_idx = path.rfind("-")
                page_number = int(path[page_idx + 1 :])
                return f"{path[:page_idx]}.pdf#page={page_number}"

            return sourcepage

    def compute_text_embedding(self, text: str):
        # There are a few ways to get embeddings. This is just one example.
        import openai

        open_ai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        open_ai_key = os.getenv("AZURE_OPENAI_API_KEY")

        client = openai.AzureOpenAI(
            azure_endpoint=open_ai_endpoint,
            api_key=open_ai_key,
            api_version="2023-03-15-preview",
        )
        embedding = client.embeddings.create(
            input=[text], model="text-embedding-ada-002"
        )

        return VectorizedQuery(
            vector=embedding.data[0].embedding,
            k_nearest_neighbors=50,
            fields="embedding",
        )

    def run(
        self,
        messages: list[dict],
        stream: bool = False,
        session_state: Any = None,
        context: dict[str, Any] = {},
    ) -> Union[dict[str, Any], AsyncGenerator[dict[str, Any], None]]:
        raise NotImplementedError
