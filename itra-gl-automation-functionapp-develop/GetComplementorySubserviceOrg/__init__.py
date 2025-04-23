from calendar import c
import json
import logging
import os
from re import sub
 
from azure.functions import QueueMessage
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from core.logger import LogError
from prepdocslib.apimanager import ApiManager
from secrets_manager import SecretsManager
from openai import AsyncOpenAI
from ..data_retrieval_rag_openai.retrievethenread import RetrieveThenReadApproach
from azure.search.documents.models import (
    QueryType
)
 
async def setup_clients():
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
        openai_max_tokens=5000,
        main_prompt_template='',
 
    )
 
 
def sanitizeResults(results):
    return [
        result
        for result in results
        if result.get("Control Objective") != "Not found" and result.get("CSOC Description") != "Not found"
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
 
async def mapSubServiceOrgsWithDescriptions(approach:RetrieveThenReadApproach,subserviceOrgs,subserviceOrg,description,blob_name:str):
    prompt = f"""You are analyzing a SOC report especially the section Complementary Subservice Organization Controls (CSOCs). Please identify if the given Description, ###""" +  description + """ ### mentioned about the Organization, ### """ + subserviceOrg + """###.
        And also find if it a generic description which don't have any information about the following subservice organizations, ### """+subserviceOrgs+"""###.
        Do not include any explanations, only provide a RFC8259 compliant JSON response following this format without deviation.
        Format : [
        {"IsRelated": "BooleanValue to specify if the Description ###""" + description + """###  is related to the Subservice Organization Name ###""" + subserviceOrg + """### or not",
         "IsAGenericDescription": "BooleanValue True if it a generic description which don't have any information about the following subservice organizations, ### """+subserviceOrgs+"""### else False",
        }]"""
    result = await approach.openai_only_prompt_read(prompt)
    return result
async def getSubServiceOrgsForControl(approach:RetrieveThenReadApproach,controlObjective:str,control:str, blob_name:str):
    prompt = f"""You are analyzing a SOC report especially the section Complementary Subservice Organization Controls (CSOCs). Please identify the subservice organizations associated with the control objective ###""" + controlObjective + """###.
        Do not include any explanations, only provide a RFC8259 compliant JSON response following this format without deviation.
        Format : [
        {"Subservice Organization": "Subservice Organization associated with or responsible for the Control Objective ###""" + controlObjective + """###" and Control ###""" + control + """###. If the subservice organization is not directly mentioned along with the control, read the statements around the control to identify the subservice organization. Subservice organization can be a generic name or unique name"
        }]"""
    result = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(1),
        session_state=None,
        search_client_message=control,
        sourcefile=blob_name,
        query_type=QueryType.FULL,
        addDefaultMessage=False,
        fetchBefore=True
    )
    return result
 
async def getComplementarySubserviceOrgData(approach:RetrieveThenReadApproach, blob_name:str,report_name:str):
    prompt = """Please identify any sections in the SOC report that mention Complementary Subservice Organization Controls (CSOCs) and the unique name of the subservice organizations associated with that corresponding control also consider exclusion condition in tag 'Exclusion:'. For each Complementary Subservice Control, provide the control id, controls objectives or control process area and the associated subservice organizations, after analyzing the text in key Source:.Each CSOC Description and associated Subservice Organization must be returned as a separate object in the JSON array if they are presented in separate rows in the source document. Do not combine multiple CSOC Descriptions and Subservice Organizations into a single object if they are listed separately. Maintain the structure as presented in the Source:. If no match is found,return an empty array. Do not include any explanations, only provide a RFC8259 compliant JSON response following this format without deviation.
       
       Format :
        ["Control Objective": "Control objective number associated with the CSOC, if not found specify 'Not found'",
        "CSOC Description": "[List of distinct Controls corresponding of the Control objective without any service description or monitoring controls as per the SOC 1 report, if not found specify 'Not found'".]",
        "Confidence Score": "Confidence score of the result in double",
        "PageNo": "Page Number from Source content",
        }]
        Exclusion: Do not take data from Complementary User Entity Controls (CUECs) or remove the data if it is from Complementary User Entity Controls. Also, consider that controls can span across multiple pages and can be a bulleted list.
        Ensure that CSOC Description or control is treated as a separate item, whether it is a bullet point or a paragraph. And Do not pick Control Description from column Services Provided.
        If the Control Objective has different sets of CSOC Descriptions and Subservice Organizations mapping or they are in seperate table rows, set as a separate object in the data array, even if they share the same Control Objective."""
    result = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(10),
        session_state=None,
        search_client_message="Complementary Subservice Organization Controls",
        sourcefile=blob_name,
        query_type=QueryType.FULL,
        addDefaultMessage=False,
        sortBasedOnPageNo=True
    )
    rows = []
    print(result)
    result1 =sanitizeResults(result)
 
    def remove_duplicates(controls):
        unique_controls = []
        seen = set()
        for control in controls:
            # Create a unique identifier for each control based on the key fields
            identifier = (tuple(control['Control Objective']), tuple(control['CSOC Description']))
            if identifier not in seen:
                unique_controls.append(control)
                seen.add(identifier)
        return unique_controls
 
 
    result2 = remove_duplicates(result1)
    print("result 2 is ",result2)
    rows = []
 
    if result2 and len(result2) > 0:
            for control in result2:
                # Check if control is a dictionary and has a "CSOC Description"
                if not isinstance(control, dict) or control.get("CSOC Description") is None:
                    continue  # Skip to the next control instead of breaking the loop
   
                descriptions = control["CSOC Description"] if isinstance(control["CSOC Description"], list) else [control["CSOC Description"]]
                if control.get("Subservice Organization") is None:
                    subserviceOrgs = []
                else:
                    subserviceOrgs = control["Subservice Organization"] if isinstance(control["Subservice Organization"], list) else [control["Subservice Organization"]]
                isGenericDescription = False
                for description in descriptions:
                    if subserviceOrgs is None or len(subserviceOrgs) == 0:
                        subserviceOrgs = await getSubServiceOrgsForControl(approach,control['Control Objective'],description,blob_name)
                        subserviceOrgs = [subserviceOrg["Subservice Organization"] for subserviceOrg in subserviceOrgs]
                    for subserviceOrg in subserviceOrgs:
                        addcolumn=False
                        if len(subserviceOrgs) == 1 or isGenericDescription:
                            addcolumn=True
                        else:
                            data = await mapSubServiceOrgsWithDescriptions(approach,",".join(subserviceOrgs),subserviceOrg,description,blob_name)
                            if data and len(data) > 0:
                                if data[0]['IsRelated']:
                                    addcolumn=True
                                if data[0]['IsAGenericDescription']:
                                    addcolumn=True
                                    isGenericDescription = True
 
                        # Add column for addcolumn1
                        if addcolumn:
                            columns = []
                            columns.append({
                                    "ColumnKey": "tag_CSOCs_tbl_coPageReference",
                                    "ColumnValue": f"{control['Control Objective']} (PageNo#{control['PageNo']})",
                                    "ConfidenceScore": control["Confidence Score"],
                                    "PageNo": control["PageNo"],
                                    "BoundingAreas": "",
                                })
                            columns.append({
                                    "ColumnKey": "tag_CSOCs_tbl_csoc",
                                    "ColumnValue": description,
                                    "ConfidenceScore": control["Confidence Score"],
                                    "PageNo": control["PageNo"],
                                    "BoundingAreas": "",
                                })
                            columns.append({
                                    "ColumnKey": "tag_CSOCs_tbl_sso",
                                    "ColumnValue": subserviceOrg,
                                    "ConfidenceScore": control["Confidence Score"],
                                    "PageNo": control["PageNo"],
                                    "BoundingAreas": "",
                                })
                            rows.append({"PredictedColumns": columns})  
    return rows
 
 
async def main(msg: QueueMessage) -> None:
    try:
        logging.info(
            "Python queue trigger function processed a queue item: %s",
            msg.get_body().decode("utf-8"),
        )
        msg_body = json.loads(msg.get_body())
        blob_name = msg_body.get("blob_name", "")
        report_name = msg_body.get("report_name","")
        CorrelationId = msg_body.get("CorrelationId", "")
        blob_id = msg_body.get("blob_id", "")
        approach = await setup_clients()
        rows = await getComplementarySubserviceOrgData(approach, blob_name,report_name)
        print(rows)
        tableData = {
            "name":'tag_CSOCs_tbl',"PredictedRows": rows
        }
        entitiesData = []
        entitiesData.append(
        {
                "Name": "tag_CSOCs_noControlsForSubserviceOrganizations",
                "PredictedValues":[{"Value":True if len(rows) == 0 else False,"ConfidenceScore":"0","PageNo":0}]
        })
        entitiesData.append(
        {
                "Name": "tag_CSOCs_controlsEvaluated",
                "PredictedValues":[{"Value":False if len(rows) == 0 else True,"ConfidenceScore":"0","PageNo":0}]
        })
   
        result_data = {"TableEntities":[tableData],"Entities":entitiesData}
        json_string = json.dumps(result_data)
        logging.error('going to call api')
        data = {
                "documentId": blob_id,
                "extractedTagValues": json_string,
                "blobFilePath": "",
                "predictionBlobPath": "",
                "errorMessage": "",
                "sectionName":"CSOCs",
                "CorrelationId": CorrelationId
        }
        data_json = json.dumps(data)
        logging.error(data_json)
        response = ApiManager().callback_api(data_json)
        logging.error('response is ')
        logging.error(response)
    except Exception as e:
        logging.error("Error in main function: {0}".format(str(e)))
        documentName = blob_name.split('/')[-1]
        LogError(e, e,CorrelationId,blob_id,documentName)