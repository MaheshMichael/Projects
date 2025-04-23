import json
import logging
import os
import requests
from openai import AsyncOpenAI
from azure.storage.queue import (
        QueueClient
)
import base64

# from GetSOCReportData.prompts.subserviceorg import SubServiceOrganizationPromptBuilder
# from GetSOCReportData.prompts.testingException import TestingExceptionPromptBuilder
from core.logger import LogError
from prepdocslib.apimanager import ApiManager
from secrets_manager import SecretsManager
import azure.functions as func
from ..data_retrieval_rag_openai.retrievethenread import RetrieveThenReadApproach
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
CONFIG_ASK_VISION_APPROACH = "ask_vision_approach"
AZURE_STORAGE_CONTAINER = 'socdocuements'
AZURE_SEARCH_INDEX = 'aiindex'
async def setup_clients():
# Set up clients for AI Search and Storage
    [aisearch_index_name, aisearch_endpoint, aisearch_key] = SecretsManager.get_AISearchDetails()
    search_client = SearchClient(
    endpoint=aisearch_endpoint,
    index_name=aisearch_index_name,
    credential=AzureKeyCredential(aisearch_key))
    [openaiendpoint, openaikey,organization] = SecretsManager.get_OpenAIDetails()
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
            query_speller='lexicon',
            openai_temprature = 0.3
        )
def getNames(i):
    names =['referenceInformation_soc1ReportName','referenceInformation_asOfDateOrPeriodCovered','tag_subserviceOrganizations_tbl_ssoname','tag_subserviceOrganizations_tbl_scomponents']
    return names[i]
def getQuestions():
    return ["Independent Service Auditor's Report","As of date or period"]
def getTemplate(index:int,reportName = ''):
    questions = ["Please provide the name of the organization and the specific system within the organization that is being evaluated as part of the SOC report as a space seperated string. If the report is related to a subsidiary or child entity, please specify the entity name separate from the parent organization's name. \
                 The entity name and system name in a SOC 1 report can typically be found in the introductory sections of the report. The entity name is usually the name of the organization that is being evaluated, and the system name refers to the specific system or service within that organization that is being evaluated. \
                 In the introductory sections, look for phrases like \"We have examined the description of the system of [Entity Name]\" or \"related to [System Name]\". The entity name is often the name of the company or organization, and the system name is often a specific service or process that the company provides or manages.\
                And also take the text exactly as it appears in the tag Sources:",
                 "Please provide the specific period or date range for the SOC report review. Include the start and end dates for a complete timeline"]

    if index == 0:
        question = [{"EntityName":"Please provide the name of the organization that is being evaluated as part of the SOC report. If the report is related to a subsidiary or child entity, please specify the entity name separate from the parent organization's name.",
                    "SystemName":"Please provide the specific system within the organization that is being evaluated as part of the SOC report. the system name refers to the specific system or service within that organization that is being evaluated.If the system name includes associated services or offerings, please include them as well after analyzing the footnotes or references (like '1', '2', etc.) that provide additional details about the system, consider them too.",
                    "Confidence Score":"Confidence score of the result in double",
                    "PageNo":"Page Number from Source content"}]
        template = "In the introductory sections, look for phrases like \"We have examined the description of the system of [Entity Name]\" or \"related to [System Name]\". The entity name is often the name of the company or organization, and the system name is often a specific service or process that the company provides or manages.\
              Do not include any explanations, only provide a RFC8259 compliant JSON response following this \
        format without deviation Format : " + json.dumps(question)
        return template

    else:
        question = [{"Value":"Please provide the specific period or date range for the SOC report review. Include the start and end dates for a complete timeline",
                 "Confidence Score":"Confidence score of the result in double",
      "PageNo":"Page Number from Source content"}]
        template = "Do not include any explanations, only provide a RFC8259 compliant JSON response following this \
        format without deviation Format : " + json.dumps(question)
        return template

def getContext(numOfResults:int):
    return {"overrides":{"top":numOfResults,"retrieval_mode":"hybrid","semantic_ranker":True,"semantic_captions":False,"suggest_followup_questions":False,"use_oid_security_filter":False,"use_groups_security_filter":False,"vector_fields":["embedding"],"use_gpt4v":True,"gpt4v_input":"textAndImages"}}
async def main(msg: func.QueueMessage) -> None:
    try:
        logging.info('Python queue trigger function processed a queue item: %s')
        msg_body = json.loads(msg.get_body())
        CorrelationId = msg_body.get('CorrelationId','')
        blob_name = msg_body.get('blob_name','')
        blob_id = msg_body.get('blob_id','')
        approach = await setup_clients()
        questions = getQuestions()
        #Reference Information
        result = []
        reportName = ''
        for i,question in enumerate(questions):
            res = await approach.run(
                    [{"content":getTemplate(i,reportName)}],
                    stream=True,
                    context=getContext(3) if i == 0 else getContext(5),
                    session_state=None,
                    search_client_message=question,
                    sourcefile = blob_name,
                    # section= "(section eq 'Section 0')"                
            )
            logging.error('answer is %s', res)
            PredictedValues = []
            for item in res:
                if i == 0:
                    reportName = item['EntityName']
                    PredictedValues.append({"Value":item['EntityName'] + '##value-splitter##' + item['SystemName'],
                                        "ConfidenceScore":0.0 if isinstance(item['Confidence Score'],str) else item['Confidence Score'],
                                        "PageNo": 0})
                # elif i == 1:
                #     PredictedValues.append({"Value":reportName if item['Value'].lower() == 'not found' else reportName + '##value-splitter##' + item['Value'],
                #                         "ConfidenceScore":0.0 if isinstance(item['Confidence Score'],str) else item['Confidence Score'],
                #                         "PageNo": item["PageNo"][0] if isinstance(item["PageNo"],list) else item["PageNo"] })
                elif i == 1:
                    PredictedValues.append({"Value":item['Value'],
                                        "ConfidenceScore":0.0 if isinstance(item['Confidence Score'],str) else item['Confidence Score'],
                                        "PageNo": item["PageNo"][0] if isinstance(item["PageNo"],list) else item["PageNo"] })
                break
            # if i != 0:
            data = {
                "Name":getNames(i),
                "PredictedValues":PredictedValues
                }
            result.append(data)
        result_data = {"Entities":result}
        # print('result_data is ', result_data)
        json_string = json.dumps(result_data)
        logging.error('going to call api')
        data = {
            "documentId": blob_id,
            "extractedTagValues": json_string,
            "blobFilePath": "",
            "predictionBlobPath": "",
            "errorMessage": "",
            "sectionName":"Reference information",
            "correlationId": CorrelationId
            }
        data_json = json.dumps(data)
        logging.error(data_json)
        response = ApiManager().callback_api(data_json)
        logging.error(response)
        # requests.api = 'https://uscdadvecnwap0k.azurewebsites.net/api/Documents/callback'

        # headers={
        # 'Content-type':'application/json', 
        # 'Accept':'application/json'
        # } 
        # logging.error(data_json)
        # logging.error('Going to call api')
        # response = requests.post(url = requests.api,
        #                         headers=headers,
        #                         data = data_json)
        # logging.error('response is ')
        # logging.error(response)

        queue_client = QueueClient.from_connection_string(SecretsManager.SOC_QUEUE_STORAGE_ACCOUNT, "itra-socr-retrieve-subserviceorg")
        message = {"blob_id": blob_id, "blob_name":blob_name,"report_name":reportName,"CorrelationId":CorrelationId}
        message_json = json.dumps(message)
        message_bytes = message_json.encode('utf-8')
        base64_bytes = base64.b64encode(message_bytes)
        base64_message = base64_bytes.decode('utf-8')
        queue_client_test = QueueClient.from_connection_string(SecretsManager.SOC_QUEUE_STORAGE_ACCOUNT, "itra-socr-retrieve-testingexception")
        queue_client_cuec = QueueClient.from_connection_string(SecretsManager.SOC_QUEUE_STORAGE_ACCOUNT, "itra-socr-retrieve-cuec")
        queue_client_csubservice = QueueClient.from_connection_string(SecretsManager.SOC_QUEUE_STORAGE_ACCOUNT, "itra-socr-retrieve-csoc")
        queue_client_itapps = QueueClient.from_connection_string(SecretsManager.SOC_QUEUE_STORAGE_ACCOUNT, "itra-socr-retrieve-it-apps")
        queue_client.send_message(base64_message) 
        queue_client_test.send_message(base64_message)
        queue_client_cuec.send_message(base64_message)
        queue_client_csubservice.send_message(base64_message)
        queue_client_itapps.send_message(base64_message)
    except Exception as e:
        logging.error(e)
        documentName = blob_name.split('/')[-1]
        LogError(e, e,CorrelationId,blob_id,documentName)
