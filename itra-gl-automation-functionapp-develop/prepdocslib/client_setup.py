import os
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from openai import AsyncOpenAI
import openai
from data_retrieval_rag_openai.retrievethenread import RetrieveThenReadApproach
from secrets_manager import SecretsManager

async def setup_clients():
# Set up clients for AI Search and Storage
    [aisearchindex, aisearchendpoint,aisearchkey] = SecretsManager.get_AISearchDetails()
    [openaiendpoint, openaikey,organization] = SecretsManager.get_OpenAIDetails()
    search_client = SearchClient(
    endpoint=aisearchendpoint,
    index_name=aisearchindex,
    credential=AzureKeyCredential(SecretsManager.SOC_AI_SEARCH_KEY))
    os.environ["AZURE_OPENAI_API_KEY"] = openaikey
    os.environ["AZURE_OPENAI_ENDPOINT"] = openaiendpoint
    openai_client = AsyncOpenAI(
            api_key=openaikey,
            organization=organization,
            base_url=openaiendpoint
    )
    return RetrieveThenReadApproach(
            search_client=search_client,
            openai_client=openai_client,
            chatgpt_model='gpt-4',
            chatgpt_deployment='chat',
            embedding_model='text-embedding-ada-002',
            embedding_deployment='text-embedding-ada-002',
            sourcepage_field='sourcepage',
            content_field='content',
            query_language='en-us',
            query_speller='lexicon'           
        )