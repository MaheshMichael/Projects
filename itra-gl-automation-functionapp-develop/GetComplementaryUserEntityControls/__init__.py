import json
import logging
import os
import re
from azure.functions import QueueMessage
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
import openai
import requests
from core.logger import LogError
from secrets_manager import SecretsManager
from openai import AsyncOpenAI
from ..data_retrieval_rag_openai.retrievethenread import RetrieveThenReadApproach
from azure.search.documents.models import (
    QueryType
)
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from prepdocslib.apimanager import ApiManager

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
    prompt_base_template = "You are an auditor reviewing the section section testing exception in SOC report and need to answer questions based on the text provided in key Source:."
    return RetrieveThenReadApproach(
        search_client=search_client,
        openai_client=openai_client,
        chatgpt_model="gpt-4",
        chatgpt_deployment="chat",
        embedding_model="text-embedding-ada-002",
        embedding_deployment="text-embedding-ada-002",
        sourcepage_field="sourcepage",
        content_field="content",
        query_language="en-us",
        query_speller="lexicon",
        openai_temprature=0,
        openai_batch_size=6,
        main_prompt_template=prompt_base_template,
    )


def sanitizeResults(results):
    return [
        result
        for result in results
            if result.get("CUEC") != "Not found"
    ]


def getContext(noofresults):
    return {
        "overrides": {
            "top": noofresults,
            "retrieval_mode": "hybrid",
            "semantic_ranker": True,
            "semantic_captions": False,
            "suggest_followup_questions": False,
            "use_oid_security_filter": False,
            "use_groups_security_filter": False,
            "vector_fields": ["embedding"],
            "use_gpt4v": True,
            "gpt4v_input": "textAndImages",
        }
    }


async def getComplementaryUserEntityControlsData(approach:RetrieveThenReadApproach, blob_name:str):
    prompt = """Please identify any sections in the SOC report that mention Complementary User Entity Controls(CUECs) .The details may be present as a table or a list. For each Complementary user entity Control, please provide the  control id, control objectives and complementary user entity control descriptions. Use the text exactly in key Source.If no match is found,return an empty array. Exclude details from Complementary Subservice Organization Control objective.Do not include any explanations, only provide a RFC8259 compliant JSON response following this format without deviation.
        Format :
        [
            {
                "Control Objective": "Control objective number or reference from Complementary User Entity Controls table or list. If not found, specify 'Not found'",
                "CUEC": "[The exact text describing the user entity control from the source content. If the description is a bullet point or numbered list or a paragraph, list it as a separate item. If not found, specify 'Not found']",
                "Confidence Score": "Confidence score of the result in double",
                "PageNo": "Page Number from Source content",
                "Heading":"The Control Objective heading if present in the source content. If not found, specify 'Not found'"
            },
           // Repeat the structure for each bullet point or paragraph as a separate item
        ]
        Ensure that each description is treated as a separate item, whether it is a bullet point or a paragraph under the control objective heading .
        
        Exclusion: Do not take data from Complementary Subservice Organization Controls (CSOCs) or remove the data if it is from Complementary Subservice Organization Controls."""	
    
    result = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(15),
        session_state=None,
        search_client_message="Section titled Complementary User Entity controls or Complimentary User Entity Control Considerations or tables with user-entity control or tables with Complementary User Entity controls or tables with User Entity Controls",
        sourcefile=blob_name,
        query_type=QueryType.SEMANTIC,
        addDefaultMessage = False,
    )
    return result
    #return sanitizeResults(result)



async def main(msg: QueueMessage) -> None:
    try:
        logging.info(
            "Python queue trigger function processed a queue item: %s",
            msg.get_body().decode("utf-8"),
        )
        msg_body = json.loads(msg.get_body())
        CorrelationId = msg_body.get("CorrelationId", "")
        blob_name = msg_body.get("blob_name", "")
        blob_id = msg_body.get("blob_id", "")
        approach = await setup_clients()
        data = await getComplementaryUserEntityControlsData(approach, blob_name)
        
        result = data
        finalResult =sanitizeResults(result)
        rows = []

        for item in finalResult:
            controlObjective = item["Control Objective"] 
            cuec = item["CUEC"]
            heading = item["Heading"]

            if controlObjective == "Not found":
                if re.search("Control Objective", heading, re.IGNORECASE):
                    controlObjective = heading
                elif re.search(r'user entity control|user-entity control', heading, re.IGNORECASE):
                    controlObjective = ""
                else:
                    continue            
           
            if isinstance(cuec, str) == True:
                cuec = [cuec]                
            
            for itemCuec in cuec:
                # Check if heading is not a number and not 'Complementary User Entity Control' or 'user entity control' (ignoring case)
                if not heading.isdigit() and not re.match(r'^(complementary user entity controls|user entity controls|complementary user entity control|user entity control)$', heading, re.I) and not heading == "Not found":
                    # If so, concatenate heading and itemCuec
                    itemCuec = heading + "\n\n" + itemCuec
                else:
                    # Otherwise, itemCuec is just itemCuec
                    itemCuec = itemCuec

                columns = []
                columns.append(
                    {
                        "ColumnKey": "tag_CUECs_tbl_controlObjectiveAndPageNo",
                        "ColumnValue": controlObjective + " (Page #" + str(item["PageNo"]) + ")",
                        "ConfidenceScore": item["Confidence Score"],
                        #"PageNo": item["PageNo"],
                        "PageNo": 0,
                        "BoundingAreas": "",
                    }
                )
                columns.append(
                    {
                        "ColumnKey": "tag_CUECs_tbl_controlname",
                        "ColumnValue": itemCuec,
                        "ConfidenceScore": item["Confidence Score"],
                        "PageNo": 0,
                        "BoundingAreas": "",
                    }
                )
                
                rows.append({"PredictedColumns": columns})
                    
        tableData = {"Name": "tag_CUECs_tbl", "PredictedRows": rows}
        isNoCuecPresent = True
        noControlsEvaluated = False
        controlsEvaluated = False
        if(len(tableData["PredictedRows"]) > 0):
            isNoCuecPresent = False
            controlsEvaluated = True
        
        entitiesData = []
        entitiesData.append(
            {
                "Name": "tag_CUECs_noCUECs",
                "PredictedValues":[{"Value":isNoCuecPresent,"ConfidenceScore":"0","PageNo":"0"}]
            })
        entitiesData.append(
            {
                "Name": "tag_CUECs_noControlsEvaluated",
                "PredictedValues":[{"Value":noControlsEvaluated,"ConfidenceScore":"0","PageNo":"0"}]
            })
        entitiesData.append(
            {
                "Name": "tag_CUECs_controlsEvaluated",
                "PredictedValues":[{"Value":controlsEvaluated,"ConfidenceScore":"0","PageNo":"0"}]
            }
            )
        

        result_data = {"TableEntities":[tableData], "Entities":entitiesData}
        json_string = json.dumps(result_data)
        
        data = {
                "documentId": blob_id,
                "extractedTagValues": json_string,
                "blobFilePath": "",
                "predictionBlobPath": "",
                "errorMessage": "",
                "sectionName":"CUECs",
                "CorrelationId": CorrelationId
        }
        data_json = json.dumps(data)
        response = ApiManager().callback_api(data_json)
    except Exception as e:
        documentName = blob_name.split('/')[-1]
        LogError(e, e,CorrelationId,blob_id,documentName)
        logging.error('An error occurred: %s', str(e))