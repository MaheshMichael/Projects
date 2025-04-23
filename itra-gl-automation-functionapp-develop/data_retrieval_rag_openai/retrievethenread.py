import json
import os
import random
import re
import time
from typing import Any, AsyncGenerator, Optional, Union
 
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorQuery
from openai import AsyncOpenAI
import openai
from core.utils import calculate_token_length, getTokenLimit
 
from secrets_manager import SecretsManager
 
from .approach import Approach
from ..core.messagebuilder import MessageBuilder
import logging
from azure.search.documents.models import (
    QueryType
)
# Replace these with your own values, either in environment variables or directly here
AZURE_STORAGE_ACCOUNT = os.getenv("AZURE_STORAGE_ACCOUNT")
AZURE_STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER")
 
 
class RetrieveThenReadApproach(Approach):
    """
    Simple retrieve-then-read implementation, using the AI Search and OpenAI APIs directly. It first retrieves
    top documents from search, then constructs a prompt with them, and then uses OpenAI to generate an completion
    (answer) with that prompt.
    """
 
    system_chat_template = (
        "You are an auditor reviewing a SOC 1 report and need to answer questions based on the text provided in key Source:."
    )
 
    def __init__(
        self,
        *,
        search_client: SearchClient,
        # auth_helper: Optional[AuthenticationHelper],
        openai_client: AsyncOpenAI,
        chatgpt_model: str,
        chatgpt_deployment: Optional[str],  # Not needed for non-Azure OpenAI
        embedding_model: str,
        embedding_deployment: Optional[str],  # Not needed for non-Azure OpenAI or for retrieval_mode="text"
        sourcepage_field: str,
        content_field: str,
        query_language: str,
        query_speller: str,
        main_prompt_template: str = None,
        openai_chatgpt_model: str = "gpt-4",
        openai_temprature: float = 0.3,
        openai_max_tokens: int = 4000,
        openai_retries: int = 5,
        openai_batch_size: int = 4
    ):
        self.search_client = search_client
        self.chatgpt_deployment = chatgpt_deployment
        self.openai_client = openai_client
        # self.auth_helper = auth_helper
        self.chatgpt_model = chatgpt_model
        self.embedding_model = embedding_model
        self.chatgpt_deployment = chatgpt_deployment
        self.embedding_deployment = embedding_deployment
        self.sourcepage_field = sourcepage_field
        self.content_field = content_field
        self.query_language = query_language
        self.query_speller = query_speller
 
        self.openai_chatgpt_model = openai_chatgpt_model
        self.openai_temprature = openai_temprature
        self.openai_max_tokens = openai_max_tokens
        self.openai_retries = openai_retries
        self.openai_batch_size = openai_batch_size
        self.main_prompt_template = main_prompt_template
    async def remove_similar_results(self, results,content = None):
        max_retries = 5
        message_builder = MessageBuilder(self.system_chat_template, self.chatgpt_model,False)
        if content is not None:
            message_builder.insert_message("user", content + json.dumps(results))
        else:
            usercontent = 'From the given objects in tag Sources:, select unique ones after removing duplicates by comparing similar names in Name field\nDo not include any explanations, only provide a RFC8259 compliant JSON response'
            message_builder.insert_message("user", usercontent+json.dumps(results))
        finaldata = []
        for i in range(self.openai_retries):
            try:
                chat_completion = (
                    openai.chat.completions.create(
                        # Azure Open AI takes the deployment name as the model name
                        model=self.openai_chatgpt_model,
                        messages=message_builder.messages,  # Define the "message_builder" variable
                        temperature=self.openai_temprature,
                        max_tokens=self.openai_max_tokens,
                        n=1,
                    )
                ).model_dump()
                if chat_completion["choices"][0]["message"]['content'] != "":
                    res = json.loads(chat_completion["choices"][0]["message"]['content'])
                    finaldata.extend(res)
                    return finaldata
                break
            except Exception as e:
                if '429' in str(e) and i < max_retries - 1:
                    match = re.search(r'Please retry after (\d+) second', str(e))
                    if match:
                        wait_time = int(match.group(1))
                        time.sleep(wait_time)
                    else:
                        wait_time = (2 ** i) + random.random()
                        time.sleep(wait_time)
                else:
                    raise
                logging.error('error is %s', e)
    async def openai_only_prompt_read(self,results):
        max_retries = 5
        message_builder = MessageBuilder(self.system_chat_template, self.chatgpt_model,False)
        message_builder.insert_message("user", results)
        finaldata = []
        for i in range(self.openai_retries):
            try:
                chat_completion = (
                    openai.chat.completions.create(
                        # Azure Open AI takes the deployment name as the model name
                        model=self.openai_chatgpt_model,
                        messages=message_builder.messages,  # Define the "message_builder" variable
                        temperature=self.openai_temprature,
                        max_tokens=3202,
                        n=1,
                    )
                ).model_dump()
                if chat_completion["choices"][0]["message"]['content'] != "":
                    try:
                        res = json.loads(chat_completion["choices"][0]["message"]['content'])
                        if isinstance(res,list):
                            finaldata.extend(res)
                        else:
                            finaldata.append(res)
                    except Exception as e:
                        logging.error('error is %s', e)
                    return finaldata
                break
            except Exception as e:
                if '429' in str(e) and i < max_retries - 1:
                    match = re.search(r'Please retry after (\d+) second', str(e))
                    if match:
                        wait_time = int(match.group(1))
                        time.sleep(wait_time)
                    else:
                        wait_time = (2 ** i) + random.random()
                        time.sleep(wait_time)
                else:
                    raise
                logging.error('error is %s', e)
    async def openai_only_prompt(self,results,content = None):
        max_retries = 5
        message_builder = MessageBuilder(self.system_chat_template, self.chatgpt_model,False)
        message_builder.insert_message("user", content + json.dumps(results))
        finaldata = []
        for i in range(self.openai_retries):
            try:
                chat_completion = (
                    openai.chat.completions.create(
                        # Azure Open AI takes the deployment name as the model name
                        model=self.openai_chatgpt_model,
                        messages=message_builder.messages,  # Define the "message_builder" variable
                        temperature=self.openai_temprature,
                        max_tokens=self.openai_max_tokens,
                        n=1,
                    )
                ).model_dump()
                if chat_completion["choices"][0]["message"]['content'] != "":
                    res = json.loads(chat_completion["choices"][0]["message"]['content'])
                    finaldata.extend(res)
                    return finaldata
                break
            except Exception as e:
                if '429' in str(e) and i < max_retries - 1:
                    match = re.search(r'Please retry after (\d+) second', str(e))
                    if match:
                        wait_time = int(match.group(1))
                        time.sleep(wait_time)
                    else:
                        wait_time = (2 ** i) + random.random()
                        time.sleep(wait_time)
                else:
                    raise
                logging.error('error is %s', e)
    async def remove_duplicates(self, results,content = None):
        max_retries = 5
        message_builder = MessageBuilder(self.system_chat_template, self.chatgpt_model,False)
        if content is not None:
            message_builder.insert_message("user", content + json.dumps(results))
        else:
            usercontent = 'From the given objects in tag Sources:, select unique ones after removing duplicates by comparing similar names in Name field and please note if the name field contains a combination of names (ex:- FIS JPM MATRIX Evertec) not include such an entry and just list only indvidual names \nDo not include any explanations, only provide a RFC8259 compliant JSON response.'
            message_builder.insert_message("user", usercontent+json.dumps(results))
        finaldata = []
        for i in range(self.openai_retries):
            try:
                chat_completion = (
                    openai.chat.completions.create(
                        # Azure Open AI takes the deployment name as the model name
                        model=self.openai_chatgpt_model,
                        messages=message_builder.messages,  # Define the "message_builder" variable
                        temperature=self.openai_temprature,
                        max_tokens=self.openai_max_tokens,
                        n=1,
                    )
                ).model_dump()
                if chat_completion["choices"][0]["message"]['content'] != "":
                    res = json.loads(chat_completion["choices"][0]["message"]['content'])
                    finaldata.extend(res)
                    return finaldata
                break
            except Exception as e:
                if '429' in str(e) and i < max_retries - 1:
                    match = re.search(r'Please retry after (\d+) second', str(e))
                    if match:
                        wait_time = int(match.group(1))
                        time.sleep(wait_time)
                    else:
                        wait_time = (2 ** i) + random.random()
                        time.sleep(wait_time)
                else:
                    raise
                logging.error('error is %s', e)
    async def run(
        self,
        messages: list[dict],
        stream: bool = False,  # Stream is not used in this approach
        session_state: Any = None,
        context: dict[str, Any] = {},
        search_client_message: str = None,
        sourcefile:str = None,
        section:str = None,
        query_type :QueryType = QueryType.SEMANTIC,
        ignore_section = False,
        addDefaultMessage = True,
        fetchExtra = False,
        exclusionCriteria = None,
        sort = False,
        sortBasedOnPageNo = False,
        fetchBefore = False
    ) -> Union[dict[str, Any], AsyncGenerator[dict[str, Any], None]]:
        q = messages[-1]["content"]
        overrides = context.get("overrides", {})
        auth_claims = context.get("auth_claims", {})
        has_text = overrides.get("retrieval_mode") in ["text", "hybrid", None]
        has_vector = overrides.get("retrieval_mode") in ["vectors", "hybrid", None]
        use_semantic_ranker = overrides.get("semantic_ranker") and has_text
        use_semantic_captions = True if overrides.get("semantic_captions") and has_text else False
        top = overrides.get("top", 3)
        filter = 'sourcefile eq ' + "'" + sourcefile + "'"
        if section and len(section) > 0:
            filter = filter + ' and ' + section
        print('filter ',filter)
        # If retrieval mode includes vectors, compute an embedding for the query
        vectors: list[VectorQuery] = []
        if has_vector:
            vectors.append(await self.compute_text_embedding(search_client_message))
 
        # Only keep the text query if the retrieval mode uses text, otherwise drop it
        query_text = search_client_message if has_text else None
        try:
            results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=query_type)
        except Exception as e:
            logging.error('error is %s', e)
            results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=QueryType.FULL)
       
        if results is None or results == [] and not ignore_section:
            filter = 'sourcefile eq ' + "'" + sourcefile + "'"
            try:
                results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=query_type)
            except Exception as e:
                logging.error('error is %s', e)
                results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=QueryType.FULL)
        # if 'Services provided by Subservice organization' in search_client_message:
        #     new_results = []
        #     # Process the search results
        #     for result in results:
        #         new_results.append(result)
        #         # Get the pdfpageno from the result
        #         pdfpageno = result.pdfpageno
        #         filter = 'sourcefile eq ' + "'" + sourcefile + "'" + ' and (pdf_page_num eq ' + str(pdfpageno - 1) + ' or pdf_page_num eq ' + str(pdfpageno - 2) + ')'
        #         try:
        #             additional_results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=query_type)
        #         except Exception as e:
        #             logging.error('error is %s', e)
        #             additional_results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=QueryType.FULL)
        #         filter1 = 'sourcefile eq ' + "'" + sourcefile + "'" + ' and (pdf_page_num eq ' + str(pdfpageno + 1) + ' or pdf_page_num eq ' + str(pdfpageno + 2) + ')'
        #         try:
        #             additional_results1 = await self.search(top, query_text, filter1, vectors, use_semantic_ranker, use_semantic_captions,query_type=query_type)
        #         except Exception as e:
        #             logging.error('error is %s', e)
        #             additional_results1 = await self.search(top, query_text, filter1, vectors, use_semantic_ranker, use_semantic_captions,query_type=QueryType.FULL)
        #         sortdata = sorted(additional_results, key=lambda x: x.pdfpageno)
        #         new_results.extend(sortdata)
        #         new_results.append(result)
        #         new_results.extend(additional_results1)
        #     results = new_results
        if fetchExtra:
            new_results = []
            for result in results:
                new_results.append(result)
                pdfpageno = result.pdfpageno
                filter = 'sourcefile eq ' + "'" + sourcefile + "'" + ' and (pdf_page_num eq ' + str(pdfpageno + 1) + ' or pdf_page_num eq ' + str(pdfpageno + 2) + ')'
                try:
                    additional_results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=query_type)
                except Exception as e:
                    logging.error('error is %s', e)
                    additional_results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=QueryType.FULL)
                sortdata = sorted(additional_results, key=lambda x: x.pdfpageno)
                new_results.extend(sortdata)
            results = new_results
        if fetchBefore:
            new_results = []
            for result in results:
                new_results.append(result)
                pdfpageno = result.pdfpageno
                filter = 'sourcefile eq ' + "'" + sourcefile + "'" + ' and (pdf_page_num eq ' + str(pdfpageno - 1) + ' or pdf_page_num eq ' + str(pdfpageno - 2) + ')'
                try:
                    additional_results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=query_type)
                except Exception as e:
                    logging.error('error is %s', e)
                    additional_results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=QueryType.FULL)
                sortdata = sorted(additional_results, key=lambda x: x.pdfpageno)
                new_results.extend(sortdata)
            results = new_results
        # Check if 'Complementary User Entity controls' is in search_client_message
        if 'Complementary User Entity controls' in search_client_message or 'Complementary Subservice Organization Controls' in search_client_message:
            new_results = []
            # Process the search results
            for result in results:
                new_results.append(result)
                # Get the pdfpageno from the result
                pdfpageno = result.pdfpageno
 
                # Search the next 3 pages
                for i in range(pdfpageno + 1, pdfpageno + 3):
                    # Perform the search
                    filter = 'sourcefile eq ' + "'" + sourcefile + "'" + ' and pdf_page_num eq ' + str(i)
                    try:
                        additional_results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=query_type)
                    except Exception as e:
                        logging.error('error is %s', e)
                        additional_results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=QueryType.FULL)
                    new_results.extend(additional_results)
            results = new_results
        elif "Management's response for ID" in search_client_message:
            new_results = []
            for result in results:
                # Get the pdfpageno from the result
                pdfpageno = result.pdfpageno
                filter = 'sourcefile eq ' + "'" + sourcefile + "'" + ' and (pdf_page_num eq ' + str(pdfpageno - 1) + ' or pdf_page_num eq ' + str(pdfpageno - 2) + ' or pdf_page_num eq ' + str(pdfpageno - 3) + ')'
                try:
                    additional_results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=query_type)
                except Exception as e:
                    logging.error('error is %s', e)
                    additional_results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=QueryType.FULL)
                sortdata = sorted(additional_results, key=lambda x: x.pdfpageno)
                new_results.extend(sortdata)
                new_results.append(result)
            results = new_results
        if sort:
            results = sorted(results, key=lambda x: x.pdfpageno)
        # elif 'Testing Controls which has' in search_client_message:
        #     new_results = []
        #     # Process the search results
        #     for result in results:
               
        #         # Get the pdfpageno from the result
        #         pdfpageno = result.pdfpageno
        #         filter = 'sourcefile eq ' + "'" + sourcefile + "'" + ' and (pdf_page_num eq ' + str(pdfpageno - 1) + ' or pdf_page_num eq ' + str(pdfpageno - 2) + ' or pdf_page_num eq ' + str(pdfpageno - 3) + ' or pdf_page_num eq ' + str(pdfpageno - 4) + ')'
        #         try:
        #             additional_results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=query_type)
        #         except Exception as e:
        #             logging.error('error is %s', e)
        #             additional_results = await self.search(top, query_text, filter, vectors, use_semantic_ranker, use_semantic_captions,query_type=QueryType.FULL)
        #         sortdata = sorted(additional_results, key=lambda x: x.pdfpageno)
        #         new_results.extend(sortdata)
        #         new_results.append(result)
        #     results = new_results
        # Remove duplicates
        distinct_results = []
        seen_ids = set()
        for result in results:
            # Check if we've seen this id before
            if result.id not in seen_ids:
                # If not, add the result to distinct_results and the id to seen_ids
                distinct_results.append(result)
                seen_ids.add(result.id)
 
        # Replace results with distinct_results
        results = distinct_results
        #results = list(dict.fromkeys(results))
        finaldata = []
        startindex = 0
        template = self.main_prompt_template or self.system_chat_template
        model = self.chatgpt_model            
        tokenlimit = getTokenLimit(self.openai_chatgpt_model)-self.openai_max_tokens
        if sortBasedOnPageNo:
            results = sorted(results, key=lambda x: x.pdfpageno)
        while startindex < len(results):
            batchsize = self.openai_batch_size if startindex+self.openai_batch_size < len(results) else len(results) - startindex
            result = results[startindex: startindex+batchsize]
            sources_content = self.get_sources_content(result, use_semantic_captions, use_image_citation=False)
            content = "\n".join(sources_content)
 
            user_content = q + "\n" + f"Sources:\n {content}"
            if exclusionCriteria is not None:
                user_content = user_content + "\n" + exclusionCriteria
            message_builder = MessageBuilder(template, model,addDefaultMessage)
            message_builder.insert_message("user", user_content)
            token_length = calculate_token_length(self.openai_chatgpt_model,' '.join(map(str, message_builder.messages)))
            while token_length > tokenlimit:
                batchsize = batchsize - 1
                result = results[startindex: startindex+batchsize]
                message_builder.remove_last_message()
                sources_content = self.get_sources_content(result, use_semantic_captions, use_image_citation=False)
                content = "\n".join(sources_content)
                user_content = q + "\n" + f"Sources:\n {content}"
                if exclusionCriteria is not None:
                    user_content = user_content + "\n\r" + exclusionCriteria
                message_builder.insert_message("user", user_content)
                token_length = calculate_token_length(self.openai_chatgpt_model,' '.join(map(str, message_builder.messages)))
            # user_content = [q]
            startindex = startindex+batchsize
            # print(message_builder.messages)
            openai.api_base = SecretsManager.SOC_OPEN_AI_SERVICE_NAME
            openai.api_version = "2023-03-15-preview"
            openai.api_key = SecretsManager.SOC_OPEN_AI_MODEL_KEY
            openai.deployment = self.openai_chatgpt_model
            for i in range(self.openai_retries):
                try:
                    chat_completion = (
                        openai.chat.completions.create(
                            # Azure Open AI takes the deployment name as the model name
                            model=self.openai_chatgpt_model,
                            messages=message_builder.messages,
                            temperature=self.openai_temprature,
                            max_tokens=self.openai_max_tokens
                        )
                    ).model_dump()
                    if chat_completion["choices"][0]["message"]['content'] != "":
                        try:
                            #logging.error(chat_completion["choices"][0]["message"]['ontent'])
                            res = json.loads(chat_completion["choices"][0]["message"]['content'])
                            
                            if isinstance(res,list):
                                finaldata.extend(res)
                            else:
                                finaldata.append(res)
                        except Exception as e:
                            logging.error('error is %s', e)
                    break
                except Exception as e:
                   
                    if '429' in str(e) and i < self.openai_retries - 1:
                        match = re.search(r'Please retry after (\d+) second', str(e))
                        if match:
                            wait_time = int(match.group(1))
                            time.sleep(wait_time)
                        else:
                            wait_time = (2 ** i) + random.random()
                            time.sleep(wait_time)
                    else:
                        raise
                    logging.error('error is %s', e)
        return finaldata
