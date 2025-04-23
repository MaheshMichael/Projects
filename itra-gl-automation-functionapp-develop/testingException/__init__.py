import json
import logging
import os

from azure.functions import QueueMessage
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
# from core.logger import LogError
from core.logger import LogError
from core.utils import is_number_and_punctuation
from prepdocslib.apimanager import ApiManager
from secrets_manager import SecretsManager
from openai import AsyncOpenAI
from ..data_retrieval_rag_openai.retrievethenread import RetrieveThenReadApproach
from azure.search.documents.models import (
    QueryType
)


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
        openai_chatgpt_model="gpt-4",
        chatgpt_deployment="chat",
        embedding_model="text-embedding-ada-002",
        embedding_deployment="text-embedding-ada-002",
        sourcepage_field="sourcepage",
        content_field="content",
        query_language="en-us",
        query_speller="lexicon",
        openai_temprature=0.3,
        openai_batch_size=6,
        openai_max_tokens=4000
        # openai_max_tokens=10000
        # main_prompt_template=prompt_base_template,
    )


def sanitizeResults(results):
    return [
        result
        for result in results
        if result.get("Control Reference").lower() != 'not found' and result.get("Description of Control Activity").lower() != "not found"
        and result.get("Results")
        and result.get("Results") != ""
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

def getSecondPromptForControlInformation():
    return (
        """Please identify any control activities mentioned in the provided SOC report where there are explicit mentions of 'exception noted' or 'deviation noted' in the test result column.Strictly consider the condition in tag 'Exclusion:'. The details will be present in a table. Ignore if it is something like 'No exception noted'. Exclude if the result is found from section 'Management Response...' or 'Management's Response..' section. If no control activities with explicit exceptions or deviations are found, return an empty array. Please provide the information in a JSON format compliant with RFC8259. JSON response should follow this format without deviation: 
        Note: If the control reference is mentioned as 'See previous page' or similar, please ignore that entry and do not include it in the results.Do not include any explanations, \
        only provide a RFC8259 compliant JSON response following this \
        format without deviation Format :"""
        + "\n"
        + """[
        {
            "Description of Control Activity": "This section provides a brief explanation of the control activity that has been implemented, if not found specify 'Not found'",
            "Control Reference": "This is the unique identifier for the control activity that has been tested,if it is simply an integer like '1,2'11', if there is an information like Control Objective number ex:- 'Control Objective 3' so append these with the number so it will come like 'Control Objective 3.11' and if there is no such unique identifier just check if it is coming under any section like control objective with number ex:- 'Control Objective 22' or 'Control Object 'number'' then pick that value so it maybe like ex:- 'Control Objective 22', if not found specify 'Not found'",
            "Results": "This section provides the results of the test of controls. If there are any exceptions or deviations noted during the testing, they will be explicitly mentioned here, no need to add any information like  'Refer to the  ...' and information about Management Response. if not found specify 'Not found'",
            "Confidence Score": "Confidence score of the result in double",
            "PageNo": "Page Number from Source content",
        }
    ]"""
        + "\n"
    )

async def getControlInformation(approach: RetrieveThenReadApproach, blob_name: str):
    prompt = (
        """Please identify any control activities mentioned in the provided SOC report in a table where there are explicit mentions of 'exception noted' or 'deviation noted' in the test result column. The details will be present only in a table.Before returning the results, carefully read the instructions in the 'Exclusion'. Ignore if it is something like 'No exception noted'. If no control activities with explicit exceptions or deviations are found and not from an explicit table, return an empty array. Please provide the information in a JSON format compliant with RFC8259. JSON response should follow this format without deviation: 
        Do not include any explanations, \
        only provide a RFC8259 compliant JSON response following this \
        format without deviation Format :"""
        + "\n"
        + """[
        {
            "Description of Control Activity": "This section provides a brief explanation of the control activity that has been implemented, if not found specify 'Not found'",
            "Control Reference": "This is the unique identifier for the control activity that has been tested, if the control reference name has some unwanted spaces remove it and return a valid name, if not found specify 'Not found'",
            "Results": "This section provides the results of the test of controls. If there are any exceptions or deviations noted during the testing, they will be explicitly mentioned here, no need to add any information like  'Refer to the  ...' and information about Management Response. if not found specify 'Not found'",
            "Confidence Score": "Confidence score of the result in double",
            "PageNo": "Page Number from Source content",
        }
    ]"""
        + "\n"
    )
    exclusion = """Exclusion: 1. Exclude entries where the control reference is mentioned as 'See previous page' or any similar phrase indicating reference to previous content. \
        2. Exclude entries where the Description of Control Activity, Control Reference and results of the test of controls are not explicitly mentioned in the table. Because a valid result will be present only in a table
        3. Exclude if the result is found from section 'Management Response...' or 'Management's Response..' section.
        4. Control reference can never be a comma seperated strings . So don't take such an entry in the results"""
    result = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(60),
        session_state=None,
        # search_client_message="Testing Controls which has exception noted or deviation noted in Test Results",
        search_client_message="Testing Controls which has 'exception noted' or 'deviation noted' or 'Exception noted' or 'Deviation noted' or 'Deviations noted' in 'Results' or 'Test Results' or 'EY Test Results' or 'Results of Tests'",
        sourcefile=blob_name,
        # section="section eq 'Section 4'",
        query_type=QueryType.SEMANTIC,
        exclusionCriteria=exclusion,
        sortBasedOnPageNo=True
    )
    newresult = []
    for control in result:
        if control['Control Reference'].lower() == 'not found' and control["PageNo"] != 0:
            pageNo = control["PageNo"]
            data = await approach.run(
                [{"content": getSecondPromptForControlInformation()}],
                stream=True,
                context=getContext(4),
                session_state=None,
                search_client_message="*",
                section="(pdf_page_num eq " + str(pageNo) + " or pdf_page_num eq " + str(pageNo-1) + " or pdf_page_num eq " + str(pageNo-2) + " or pdf_page_num eq " + str(pageNo-3) + ")",
                sourcefile=blob_name,
                # section="section eq 'Section 4'",
                query_type=QueryType.FULL,
                sort=True,
                exclusionCriteria=exclusion
            )
            if data and len(data) > 0:
                for newcontrol in data:
                    if newcontrol['Control Reference'].lower() != 'not found' and newcontrol["PageNo"] != 0:
                        newresult.append(newcontrol)
    if newresult and len(newresult) > 0:
        result.extend(newresult)
    return sanitizeResults(result)

async def getQualifiedOrUnqualifiedReport(approach: RetrieveThenReadApproach, blob_name: str):
    prompt = (f"""Inquiry on Service Auditor's Report Qualification Status
              To determine if the service auditor's report is qualified or unqualified, and to gather further details if there are qualifications.
              Please provide the information in a JSON format compliant with RFC8259. JSON response should follow this format without deviation: """
        + "\n"
        + """[
        {
            "IsQualified": "Based on the wording provided in the Opinion Section, is the service auditor's report qualified or unqualified? Return 'true' if it is Unqualified and 'false' if it is Qualified. if not found specify 'Not Found'",
            "PageNo": "Page Number from Source content",
            "Qualifications":"If the report is qualified, please provide the specific text from the report that outlines the qualifications. If not found specify 'Not found'",
            "QualificationNotRelaventToAudit:" If the qualifications do not relate to a relevant part of the audit, please explain why the qualifications are not relevant to the key aspects of the service organization's control environment. If not found specify 'Not found'"
        }
    ]"""
        + "\n")
    result = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(10),
        session_state=None,
        search_client_message="Auditor's Opinion",
        sourcefile=blob_name,
        addDefaultMessage=False
    )
    columns = []
    isqualified = 'true'
    reportqualification = ''
    relavantpartoftheaudit  = ''

    for control in result:
        if control['IsQualified'].lower() != 'not found':
            isqualified = control['IsQualified']
            reportqualification = control['Qualifications'] if control['Qualifications'].lower() != 'not found' else ''
            relavantpartoftheaudit = control['QualificationNotRelaventToAudit'] if control['QualificationNotRelaventToAudit'].lower() != 'not found' else ''
            break
    return (isqualified,reportqualification,relavantpartoftheaudit)
async def getManagementResponseForException(
    approach: RetrieveThenReadApproach, blob_name: str, exception: str
):
    prompt = (
        f"""Please identify the management's response to the exception {exception} in the SOC report.Include the management's response even if it is presented as a mitigating procedure or similar statement. Exclude the result if it directs to another section or contains text like 'Refer to Section V for management's response'and note that the 'Exception Noted' in the 'Results of Tests' is not considered as the management's response. If the management's response is not found or directs to another section, return an empty array. Please provide the information in a JSON format compliant with RFC8259. JSON response should follow this format without deviation: """
        + "\n"
        + """[
        {
            "Management Response": "This section provides the management's response to the control activity, {controlId} that has been tested, if not found specify 'Not found' and if the management's response directs to another section or contains text like 'Refer to Section V for management's response' return 'Not Found'.Include the management's response even if it is presented as a mitigating procedure or similar statement.",
            "Additional Procedure": "Additional Procedure if any, if not found specify 'Not found'",
            "PageNo": "Page Number from Source content",
            "Confidence Score": "Confidence score of the result in double",
            "IsAudited":"This section provides the information about whether the management's response is audited or not.Value should be 'Unaudited' or 'Audited' or 'Not found'.Responses included in the testing section of a SOC 1 report are presumed to be 'Audited''.If it is from section name something like 'Other Information ... ' or 'Other Information provided by ...' , then the result is ''. If it is not from section where testing exceptions are mentioned then it is presumed to be 'Unaudited'.",

        }
    ]"""
        + "\n"
    )
    result = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(5),
        session_state=None,
        search_client_message="Management's response for ID '" + exception + "'",
        sourcefile=blob_name,
        # section="section eq '" + section + "'",
        addDefaultMessage=False
    )
    return result
async def getManagementResponse(
    approach: RetrieveThenReadApproach, blob_name: str, controlId: str
):
    prompt = (
        f"""Please identify the management's response to the control activity with the unique identifier {controlId} in the SOC report.Include the management's response even if it is presented as a mitigating procedure or similar statement. Exclude the result if it directs to another section or contains text like 'Refer to Section V for management's response'and note that the 'Exception Noted' in the 'Results of Tests' is not considered as the management's response. If the management's response is not found or directs to another section, return an empty array. Please provide the information in a JSON format compliant with RFC8259. JSON response should follow this format without deviation: """
        + "\n"
        + """[
        {
            "Management Response": "This section provides the management's response to the control activity,"""+ controlId +""" that has been tested, if not found specify 'Not found' and if the management's response directs to another section or contains text like 'Refer to Section V for management's response' return 'Not Found'.Include the management's response even if it is presented as a mitigating procedure or similar statement.",
            "Additional Procedure": "Additional Procedure if any, if not found specify 'Not found'",
            "PageNo": "Page Number from Source content",
            "Confidence Score": "Confidence score of the result in double",
            "IsAudited":"This section provides the information about whether the management's response is audited or not.Value should be 'Unaudited' or 'Audited' or 'Not found'.Responses included in the testing section of a SOC 1 report are presumed to be 'Audited''.If it is from section name something like 'Other Information ... ' or 'Other Information provided by ...' , then the result is ''. If it is not from section where testing exceptions are mentioned then it is presumed to be 'Unaudited'.",

        }
    ]"""
        + "\n"
    )
    result = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(5),
        session_state=None,
        search_client_message="Management's response for ID '" + controlId + "'",
        sourcefile=blob_name,
        # section="section eq '" + section + "'",
        addDefaultMessage=False
    )
    return result


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
        (qualified,reportqualification,relevantpartofaudit) = await getQualifiedOrUnqualifiedReport(approach,blob_name)
        
        result = await getControlInformation(approach, blob_name)
        controls = []
        rows = []
        for control in result:
            co = control["Control Reference"].replace("Control Objective","").replace("Control Number","").strip()
            if co not in controls:
                print(control['Control Reference'])
                columns=[]
                columns.append({
                    "ColumnKey": "tag_reportQualifications_testingexceptions_tbl_reference",
                    "ColumnValue":  ("CO " + control["Control Reference"] if is_number_and_punctuation(control["Control Reference"]) else control["Control Reference"] )+ "(PageNo#" + str(control["PageNo"]) + ")",
                    "ConfidenceScore": "0",
                    "PageNo": control["PageNo"] if isinstance(control["PageNo"],int) else 0,
                    "BoundingAreas": "",
                })
                columns.append({
                    "ColumnKey": "tag_reportQualifications_testingexceptions_tbl_controlRelatedToException",
                    "ColumnValue": control["Description of Control Activity"],
                    "ConfidenceScore": "0",
                    "PageNo": control["PageNo"] if isinstance(control["PageNo"],int) else 0,
                    "BoundingAreas": "",
                })
                columns.append({
                    "ColumnKey": "tag_reportQualifications_testingexceptions_tbl_testingException",
                    "ColumnValue": control["Results"],
                    "ConfidenceScore": "0",
                    "PageNo": control["PageNo"] if isinstance(control["PageNo"],int) else 0,
                    "BoundingAreas": "",
                })
                controls.append(co)
                managementResponse = await getManagementResponse(
                    approach, blob_name, control["Control Reference"]
                )
                if managementResponse[0]["Management Response"].lower() == 'not found':
                    managementResponse = await getManagementResponseForException(
                        approach, blob_name, control["Results"]
                    )
                additionalProcedure = ''
                if managementResponse[0]["Additional Procedure"].lower() != 'not found' and len(managementResponse[0]["Additional Procedure"]) > 0:
                    additionalProcedure = "Additional Procedure : " +  managementResponse[0]["Additional Procedure"]
                columns.append({
                        "ColumnKey": "tag_reportQualifications_testingexceptions_tbl_managementResponse",
                        "ColumnValue": '' if managementResponse[0]["Management Response"].lower() == 'not found' else managementResponse[0]["Management Response"] + additionalProcedure,
                        "ConfidenceScore": "0",
                        "PageNo": managementResponse[0]["PageNo"] if isinstance(managementResponse[0]["PageNo"],int) else 0,
                        "BoundingAreas": "",
                })
                columns.append({
                        "ColumnKey": "tag_reportQualifications_testingexceptions_tbl_auditedOrNot",
                        "ColumnValue": '' if managementResponse[0]["IsAudited"].lower() == 'not found' else managementResponse[0]["IsAudited"],
                        "ConfidenceScore": "0",
                        "PageNo": managementResponse[0]["PageNo"] if isinstance(managementResponse[0]["PageNo"],int) else 0,
                        "BoundingAreas": "",
                })
                if managementResponse[0]["Management Response"].lower() != 'not found' and len(managementResponse[0]["Management Response"]) > 0 :
                    rows.append({"PredictedColumns": columns})

        tableData = {
            "name":'tag_reportQualifications_testingexceptions_tbl',"PredictedRows": rows
        }
        entitiesData = []
        entitiesData.append(
        {
                "Name": "tag_reportQualifications_reportUnqualified",
                "PredictedValues":[{"Value":True if qualified == 'true' else False,"ConfidenceScore":"0","PageNo":0}]
        })
        entitiesData.append(
        {
                "Name": "tag_reportQualifications_notestingexceptions",
                "PredictedValues":[{"Value":False if len(rows) > 0 else True,"ConfidenceScore":"0","PageNo":0}]
        })
        trows = []
        tabledatareportqualification = []
        tabledatareportqualification.append({
                        "ColumnKey": "tag_reportQualifications_textofRptQualifications_tbl_txtRptQuls",
                        "ColumnValue": reportqualification,
                        "ConfidenceScore": "0",
                        "PageNo": 0,
                        "BoundingAreas": "",
                    })
        tabledatareportqualification.append({
                        "ColumnKey": "tag_reportQualifications_textofRptQualifications_tbl_explainNotRelevant",
                        "ColumnValue": relevantpartofaudit,
                        "ConfidenceScore": "0",
                        "PageNo": 0,
                        "BoundingAreas": "",
                    })
        trows.append({"PredictedColumns": tabledatareportqualification})
        ttabledata = {"name":'tag_reportQualifications_textofRptQualifications_tbl',"PredictedRows": trows}
        result_data = {"TableEntities":[tableData,ttabledata],"Entities":entitiesData}
        json_string = json.dumps(result_data)

        logging.error('going to call api')

        data = {
                "documentId": blob_id,
                "extractedTagValues": json_string,
                "blobFilePath": "",
                "predictionBlobPath": "",
                "errorMessage": "",
                "sectionName":"Rpt quals & testing exceptions",
                "CorrelationId": msg_body.get('CorrelationId','')
        }
        data_json = json.dumps(data)
        logging.error(data_json)
        response = ApiManager().callback_api(data_json)
        logging.error(response)
    except Exception as e:
        documentName = blob_name.split('/')[-1]
        LogError(e, e,CorrelationId,blob_id,documentName)
        logging.error(str(e))
