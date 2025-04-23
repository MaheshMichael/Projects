import asyncio
import base64
from ctypes import Union
from enum import Enum
import os
from queue import Queue
import tempfile
import json
import logging
from typing import Optional
from azure.storage.blob import BlobServiceClient
import azure.functions as func
from azure.core.credentials import AzureKeyCredential
from azure.storage.queue import (
        QueueClient
)

from core.logger import LogError
from secrets_manager import SecretsManager
from ..prepdocslib.embeddings import AzureOpenAIEmbeddingService, ImageEmbeddings, OpenAIEmbeddings

from ..prepdocslib.embeddings import AzureOpenAIEmbeddingService, ImageEmbeddings, OpenAIEmbeddings
from ..prepdocslib.filestrategy import DocumentAction, FileStrategy
from ..prepdocslib.pdfparser import DocumentAnalysisPdfParser, PdfParser
from ..prepdocslib.listfilestrategy import ADLSGen2ListFileStrategy, ListFileStrategy, LocalListFileStrategy
from ..prepdocslib.strategy import SearchInfo, Strategy
from ..prepdocslib.textsplitter import TextSplitter
from ..prepdocslib.listfilestrategy import File
import fitz
class QueueMessage(Enum):
    DocumentGuid = "DocumentGuid"
    FileName = "FileName"
    EngagmentId = "EngagmentId"
    ProjectId = "ProjectId"
    DocumentId = "DocumentId"
    
async def run_file_strategy(strategy: Strategy):
    [aisearch_index_name, aisearch_endpoint, aisearch_key] = SecretsManager.get_AISearchDetails()
    search_info = SearchInfo(
        endpoint=aisearch_endpoint,
        credential=AzureKeyCredential(aisearch_key),
        index_name=aisearch_index_name,
        verbose= True,
    )
    await strategy.setup(search_info)
    return await strategy.run(search_info)

async def setup_file_strategy(file) -> FileStrategy:

    [documentIntelligenceEndpoint, documentIntelligenceKey] = SecretsManager.get_DocumentIntelligenceDetails()
    [openaiendpoint, openaikey,organization] = SecretsManager.get_OpenAIDetails()
    pdf_parser: PdfParser
    pdf_parser = DocumentAnalysisPdfParser(
        endpoint=documentIntelligenceEndpoint,
        credential=AzureKeyCredential(documentIntelligenceKey)
    )
    [openaiservice, openaideployment] = SecretsManager.get_openAiServiceDetails()

    embeddings: Optional[OpenAIEmbeddings] = None
    embeddings = AzureOpenAIEmbeddingService(
            open_ai_service=openaiservice,
            open_ai_deployment=openaideployment,
            open_ai_model_name=openaideployment,
            credential=AzureKeyCredential(openaikey),
            disable_batch=False,
            verbose=True,
        )
    image_embeddings: Optional[ImageEmbeddings] = None

    print("Processing files...")
    list_file_strategy: ListFileStrategy
    list_file_strategy = ADLSGen2ListFileStrategy(
            data_lake_storage_account=SecretsManager.SOC_DELTA_LAKE_STORAGE_ACCOUNT,
            data_lake_filesystem=SecretsManager.SOC_DATA_STORAGE_ACCOUNT_CONTAINER_NAME,
            data_lake_path=None,
            credential=AzureKeyCredential(SecretsManager.SOC_DELTA_LAKE_STORAGE_ACCOUNT_KEY),
            verbose=True,
        )
    document_action = DocumentAction.Add

    return FileStrategy(
        list_file_strategy=list_file_strategy,
        pdf_parser=pdf_parser,
        text_splitter=TextSplitter(has_image_embeddings=False),
        document_action=document_action,
        embeddings=embeddings,
        image_embeddings=image_embeddings,
        search_analyzer_name='en.microsoft',
        use_acls=False,
        category=None,
        file=file,
    )

def recover_embedded_files(file : File):
    doc = fitz.open(stream=file.content, filetype="pdf")
    if doc.page_count >= 5:
        doc.close()
        return None,None
    for page in doc:
        annots = page.annots()
        for annot in annots:
            if annot.type[0] == 17:
                file_data = annot.get_file()
                if file_data:
                    doc.close()
                    return file_data,None
    doc.close()
    return None,'Error'

async def main(msg: func.QueueMessage) -> None:
    try:
        logging.error(
            "Python queue trigger function processed a queue item: %s",
            msg.get_body().decode("utf-8"),
        )
        msg_body = json.loads(msg.get_body().decode('utf-8'))
        logging.error(msg_body)
        CorrelationId  = msg_body.get('CorrelationId','')
        blob_name = msg_body.get(QueueMessage.FileName.value,'')
        blob_id = msg_body.get(QueueMessage.DocumentId.value,'')
        # blob_guid = msg_body.get(QueueMessage.DocumentGuid.value,'')
        blob_engagement_id = msg_body.get(QueueMessage.EngagmentId.value,'')
        blob_project_id = msg_body.get(QueueMessage.ProjectId.value,'')
      #  Connect to the storage account and Get the PDF file from the storage account
        blob_service_client = BlobServiceClient.from_connection_string(SecretsManager.SOC_DATA_STORAGE_ACCOUNT)
        container_client = blob_service_client.get_container_client(SecretsManager.SOC_DATA_STORAGE_ACCOUNT_CONTAINER_NAME)
        blob_client = container_client.get_blob_client(f'uploads/{blob_project_id}/{blob_id}/{blob_name}')
        temp_dir = os.path.join(blob_name)
        with open(temp_dir, "wb") as pdf_file:
            pdf_file = File(content =blob_client.download_blob().readall(),name=f'{blob_project_id}/{blob_id}/{blob_name}',id=blob_id)
        file,error = recover_embedded_files(pdf_file)
        if error == 'Error':
            print('The uploaded PDF could not be read. Please generate a new PDF file and attempt to upload it again')
            raise Exception('The uploaded PDF could not be read. Please generate a new PDF file and attempt to upload it again')
        if file != None:
            pdf_file.content = file      
        logging.error('PDF file downloaded: %s', blob_name)
        file_strategy = await setup_file_strategy(pdf_file)
        response = await run_file_strategy(file_strategy)
        logging.error("success")
        if(response):
            logging.error('sending message to queue')
            queue_client = QueueClient.from_connection_string(SecretsManager.SOC_QUEUE_STORAGE_ACCOUNT, "itra-socr-retrievereport")
            message = {"blob_id": blob_id, "blob_name":f'{blob_project_id}/{blob_id}/{blob_name}',"CorrelationId":CorrelationId}
            message_json = json.dumps(message)
            message_bytes = message_json.encode('utf-8')
            base64_bytes = base64.b64encode(message_bytes)
            base64_message = base64_bytes.decode('utf-8')
            queue_client.send_message(base64_message,visibility_timeout=300) 
            
    except Exception as e:
        logging.error('An error occurred: %s', str(e))
        documentName = blob_name.split('/')[-1]
        LogError(e, e,CorrelationId,blob_id,documentName)
        



        

