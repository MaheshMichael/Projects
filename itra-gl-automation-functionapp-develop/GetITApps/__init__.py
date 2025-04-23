import json
import logging
from math import e
import os
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
    prompt_base_template = "You are an auditor reviewing the system description that is mentioned in the SOC 1 report and need to answer questions based on the text provided in key Source:."
    return RetrieveThenReadApproach(
        search_client=search_client,
        openai_client=openai_client,
        chatgpt_model="gpt-4-32k",
        chatgpt_deployment="chat",
        embedding_model="text-embedding-ada-002",
        embedding_deployment="text-embedding-ada-002",
        sourcepage_field="sourcepage",
        content_field="content",
        query_language="en-us",
        openai_chatgpt_model="gpt-4-32k",
        query_speller="lexicon",
        openai_temprature=0.5,
        main_prompt_template=prompt_base_template,
        openai_batch_size=10,
        openai_max_tokens=20000

    )


def sanitizeResults(results):
    return [
        result
        for result in results
        if result.get("Description of Control Activity") != "Not found"
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
async def GetProcessPageRange(approach: RetrieveThenReadApproach, blob_name: str):
    prompt = (
        "Please review the content of SOC( System and Organization Controls) Report in the following key 'Sources:' and identify any statements related to change mangement, logical access or logical security, jobs monitoring or background jobs. Do not provide any further explanation. Please provide the information in a JSON format compliant with RFC8259. JSON response should follow this format without deviation:"
        + "\n"
        + """[
        {
            "ChangeManagement": "Page number or page numbers which has description of change management. If more than one page found provide it like (e.g.,Page 35,Page 36 etc). If not found provide an empty string.",
            "MangeAccess": "Page number or page numbers which has description of logical security or access. If more than one page found provide it like (e.g.,Page 35,Page 36 etc). If not found provide an empty string.",
            "Job": "Page number or page numbers which has description of monitoring or background jobs. If more than one page found provide it like (e.g.,Page 35,Page 36 etc). If not found provide an empty string.",
    ]      
    Exclusion: Avoid listing page numbers referring to control objectives with generic descriptions related to change management, logical access and job monitoring where there is no specific information about IT applications.
    """
     + "\n"
    )
   
    result = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(20),
        session_state=None,
        search_client_message="change management and change request or logical access and logical secuity or background processing and job monitoring and Control M and scheduling",
        sourcefile=blob_name,
        #section="section eq 'section 3'",
        query_type=QueryType.FULL,
        addDefaultMessage=False
    )
    print(result)
    return result

async def GetChangeProcessControls(approach: RetrieveThenReadApproach,blob_name:str,processPageRange:str):
    prompt = (
        "Please review the content of SOC( System and Organization Controls) Report in the following key 'Sources:' and identify control objectives and controls which are defined specifically for change mangement process. This involves control objective and controls related to changing existing programs or adding new IT programs. If any controls are found, then segregate them into control to ControlObject1 and ControlObjective2 defined the following JSON format based on the description provided for controls. ControlObjective1 should include control objectives or controls related to the change requests or change management to the existing applications or adding new IT applications. ControlObjective2 should include control activities related to the restriction that developers cannot move unauthorized or untested programs into the production environment. Please provide the information in a JSON format compliant with RFC8259. JSON response should follow this format without deviation and do not add any explanation:"
        + "\n"
        + """[
        {
            "ControlsExists": "Indicate 'Yes' if the SOC report content includes relevant control objective related to change management, otherwise 'No'.",
            "ControlObjective1": "This is the unique identifier for the controls related to the change management process such as changing existing programs or adding new IT programs. Exclude general controls like version control system or code review system. If more control objectives found, then provide a comma-separated string of the control objective numbers along with page number (e.g.,3.3 (page#30), 3.2(page#31), etc.). If no control activity found provide an empty string.",
            "ControlObjective2": "This is the unique identifier for the controls related to the change management process such as evelopers move unauthorized or untested programs into the production environment. Exclude general controls like version control system or code review system. If more control objectives found, then provide a comma-separated string of the control objective numbers (e.g.,3.3 (page#30), 3.2(page#31), etc.). If no control activity found provide an empty string.",
        }
    ]"""
        + "\n"
    )
    
    result = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(10),
        session_state=None,
        search_client_message="Testing Controls which has 'exception noted' or 'deviation noted' or 'Exception noted' or 'Deviation noted' or 'Deviations noted' in 'Results' or 'Test Results' or 'EY Test Results' or 'Results of Tests'.",
        sourcefile=blob_name,
        section="section eq 'Section 4'",
        query_type=QueryType.FULL,
        addDefaultMessage=False
    )
    controlExists = 'No'
    controlObjectives1 = ''
    controlObjectives2 = ''
    refPageNo = ''
   
    if processPageRange != None and len(processPageRange) > 0:
       if processPageRange[0].get("ChangeManagement") != '':
            refPageNo = processPageRange[0].get("ChangeManagement")
       
    i = 0
    for row in result:
        if row.get("ControlObjective1") != 'Not found' or \
           row.get("ControlObjective2") != 'Not found':
            controlExists = 'Yes'

        controlObjectives1 = controlObjectives1 + (',' if i != 0 else '') + str(row["ControlObjective1"])
        controlObjectives2 = controlObjectives2 + (',' if i != 0 else '') + str(row["ControlObjective2"])
        i = i+1
    columns = []
    trows = []
    columns.extend([
    {
        "ColumnKey": "tag_IT_changeProcess_tbl_has_control_objectives_defined",
        "ColumnValue": controlExists,
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_changeProcess_tbl_referenceWorkpaper",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_changeProcess_tbl_referencePageNo",
        "ColumnValue": refPageNo,
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_changeProcess_tbl_substantiveStrategy",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_changeProcess_tbl_SA1",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_changeProcess_tbl_SA2",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_changeProcess_tbl_controlsReliance",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_changeProcess_tbl_CR1",
        "ColumnValue": controlObjectives1,
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_changeProcess_tbl_CR2",
        "ColumnValue": " ".join(controlObjectives2),
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    }
    ])
    return columns

async def IsITGeneralControlsCarvedOut(approach: RetrieveThenReadApproach,blob_name: str,reportName: str) -> dict:
    rows = []
    base = f""" Identify the area which mentions about 'Information Technology General Controls' or 'ITGC' in the SOC report specifically mentioned under the heading 'Description of {reportName}' . Then look for specific statements says Scope of 'ITGC' or 'Information Technology General Controls' or 'IT infrastructure support' and see if those are carved out or handled or provide as part of another subservice organization. Information Technolgy controls are the controls which manage processes like like  logical access, change management, job scheduling, incident, problem management, backup data and physical access which are basically the IT processes or controls tested in the SOC report. A subservice organization can also be an internal group within the entity that supports specific operations or systems.In some cases,not all these process are handled or completely carved out in a separate report or managed by a different subservice organization. Return true for below property 'IsItgcCarvedOutCompletely' only if all of them are carved out. If in case some processes are still managed in this report currently being audited, then return as false. Do not include any explanations, only provide a RFC8259 compliant JSON response following this format without deviation.  """
    format = """ Format :
                {
                    "IsItgcCarvedOutCompletely": "Boolean value to specify if the scope of 'Information Technology General Controls' or 'ITGC' are carved out or 'ITGC' or 'Information Technology General Controls' or 'IT infrastructure support' and see if those are carved out or handled or provide as part of another subservice organization. Set this as true if it is handled  or carved out or mentioned as part of another subservice organization, otherwise set this as false.",
                }"""
 
    prompt = base + "\n"+format
    data = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(10),
        session_state=None,                             
        search_client_message="Scope of this Report or ITGC or Information Technology General Controls or Infrastructure Controls or Service Provided",
        addDefaultMessage=True,
        sourcefile=blob_name,
        query_type=QueryType.SEMANTIC
        # section="(section eq 'Section 3')"
    )
    print(data)
    #Get subservice organizations, service provided and check if there is organization is empty
    #Scenario 1: If organization is empty and service provided is empty then return empty array
    try:
        if data == None or len(data) == 0:
            return {"IsItgcCarvedOutCompletely" : ""}
        else:
            return data
    except Exception as e:
        print(e)
        return {"IsItgcCarvedOutCompletely":False}
        
async def GetAccessProcessControls(approach: RetrieveThenReadApproach,blob_name:str,processPageRange:dict):
    prompt = (
        "Please identify any control activities mentioned in the provided SOC report where there are explicit mentions basic access process risks like The service organization's IT environment is not secure due to inappropriate security settings, Access requests for IT privileged users and business users of relevant components of the IT service organization's environment are inappropriate, Access rights do not stay appropriate over time in the control description column or as a common description or control description. And within this identified control segregate control to ControlObject1, ControlObjective2 and ControlObjective3 based on the description provided for controls. ControlObjective1 should include control activities which mention service organization's IT environment is not secure due to inappropriate security settings.  ControlObjective2 should include control activities which mention ccess requests for IT privileged users and business users of relevant components of the IT service organization's environment are inappropriate. ControlObjective3 should include control activities which mention access rights do not stay appropriate over time. Please provide the information in a JSON format compliant with RFC8259. JSON response should follow this format without deviation:"
        + "\n"
        + """[
        {
            "ControlsExists": "Indicate whether the SOC1 report includes control activities which are related to security settings or managing access processes. Set the value as 'Yes' if such information is included.",
            "ControlObjective1": "This is the unique identifier for the control activity along with respective page number which has information related to the service organization's IT environment which is not secure due to Inadequate security configurations or Insufficient security measures or inappropriate security settings. If more than one control activities found, then provide a comma-separated string for control objective number (e.g.,3.3 (page#30), 3.2 (page#31), etc.). If not found return 'Not found'.",
            "ControlObjective2": This is the unique identifier for the control activity along with respective page number which has inappropriate access requests for IT privileged users and business users of the IT service organization's environment. If more control activities found, then provide a comma-separated string for control objective number (e.g.,3.3 (page#30), 3.2 (page#31), etc.). If not found return 'Not found'.",
            "ControlObjective3": "This is the unique identifier for the control activity along with respective page number which mentions about the access rights which do not stay appropriate over time. If more control activities found, then provide a comma-separated string for control objective number (e.g.,3.3 (page#30), 3.2 (page#31), etc.). If not found return 'Not found'.",
        }
    ]"""
        + "\n"
    )

    result = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(30),
        session_state=None,
        search_client_message="Testing Controls which has exception noted or deviation noted or logical access or physical security in the Test Results",
        sourcefile=blob_name,
        section="section eq 'Section 4'",
        query_type=QueryType.FULL,
        addDefaultMessage=False
    )
    controlObjectives1 = ''
    controlObjectives2 = ''
    controlObjectives3 = ''
    controlExists = 'No'
    refPageNo = ''
    i = 0
    if processPageRange != None and len(processPageRange) > 0:
       if processPageRange[0].get("MangeAccess") != '':
            refPageNo = processPageRange[0].get("MangeAccess")
    for row in result:
        if row.get("ControlObjective1") != 'Not found' or \
           row.get("ControlObjective2") != 'Not found' or row.get("ControlObjective3") != 'Not found':
            controlExists = 'Yes'

        controlObjectives1 = controlObjectives1  + ((',' if i != 0 else '') + str(row["ControlObjective1"] ) if row["ControlObjective1"] != 'Not found' else '')
        controlObjectives2 = controlObjectives2 + ((',' if i != 0 else '') + str(row["ControlObjective2"]) if row["ControlObjective1"] != 'Not found' else '')
        controlObjectives3 = controlObjectives3 + ((',' if i != 0 else '') + str(row["ControlObjective3"]) if row["ControlObjective1"] != 'Not found' else '')
        i = i+1

    columns = []
    trows = []
    columns.extend([
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_has_control_objectives_defined",
        "ColumnValue": controlExists,
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_referenceWorkpaper",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_referencePageNo",
        "ColumnValue": refPageNo,
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_substantiveStrategy",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_SA3",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_SA4",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_controlsReliance",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_CR3",
        "ColumnValue": controlObjectives1,
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_CR4",
        "ColumnValue": controlObjectives2,
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_CR5",
        "ColumnValue": controlObjectives3,
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    }
    ])
    return columns
     
   
        
async def GetAllControls(approach: RetrieveThenReadApproach,blob_name:str):
    prompt = (
        "Please identify any control activities mentioned in the provided SOC report where there are explicit mentions of security settings or manage user access in the decription column. Exclude if the result is found from section 'Management Response' section. If no control activities with explicit exceptions or deviations are found, return an empty array. If control activities found return JSON response in the following format without deviation:  Please provide the information in a JSON format compliant with RFC8259. "
        + "\n"
        + """[
        {
            "ControlsExists": "Indicate whether the SOC1 report includes control activities which are related to security settings. Set the value as 'Yes' if such information is included.",
            "ControlObjective1": "This is the unique identifier for the control activity related to the security settings to the existing applications or adding new IT applications. If more control activities found, then provide a comma-separated string.",
            "ControlObjective2": "This is the unique identifier for the control activity related to use privileges or access related to IT infrastructure. If more control activities found, then provide a comma-separated string.",
            "ControlObjective3": "This is the unique identifier for the control activity related to use privileges or access related to IT infrastructure which ends on a timely manner or appropriately when that user's role got changed or moved to a different team. If more control activities found, then provide a comma-separated string.",
            "Confiden ceScore": "Provide a numeric confidence score between 0.00 and 1.00, reflecting your level of assurance that the SOC1 report accurately represents the change management or change request controls for the application.",
            "PageNo": "List of page numbers in the SOC1 report where the information about change management controls is found."
        }
    ]"""
        + "\n"
    )

    result = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(10),
        session_state=None,
        search_client_message="Testing Controls which has exception noted or deviation noted in Test Results",
        sourcefile=blob_name,
        section="section eq 'Section 4'",
        query_type=QueryType.FULL
    )
    controlObjectives1 = ''
    controlObjectives2 = ''
    controlObjectives3 = ''
    pageNos = []
    i = 0
    for row in result:
        numbers = [int(x) for x in row["PageNo"].split(', ')]
        pageNos.extend(numbers)
        controlObjectives1 = controlObjectives1 + (',' if i != 0 else '') + str(row["ControlObjective1"])
        controlObjectives2 = controlObjectives2 + (',' if i != 0 else '') + str(row["ControlObjective2"])
        controlObjectives3 = controlObjectives3 + (',' if i != 0 else '') + str(row["ControlObjective3"])
        i = i+1

    columns = []
    trows = []
    columns.extend([
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_has_control_objectives_defined",
        "ColumnValue": "Yes",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_referenceWorkpaper",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_referencePageNo",
        "ColumnValue": "Pages " +  str(min(pageNos)) + " - " + str(max(pageNos)) if len(pageNos) > 0 else "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_substantiveStrategy",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_SA3",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_SA4",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_controlsReliance",
        "ColumnValue": "",
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_CR3",
        "ColumnValue": controlObjectives1,
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_CR4",
        "ColumnValue": controlObjectives2,
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    },
    {
        "ColumnKey": "tag_IT_accessProcess_tbl_CR5",
        "ColumnValue": controlObjectives3,
        "ConfidenceScore": "0",
        "PageNo": 0,
        "BoundingAreas": ""
    }
    ])
    return columns

async def GetJobMonitorControls(approach: RetrieveThenReadApproach,blob_name:str,processPageRange:dict):
    prompt = (
        "Please identify any control activities mentioned in the provided SOC report where there are explicit mentions of jobs or job scheduling or job monitoring like Jobs are scheduled inaccurately,Access to the job scheduler is inappropriate, Issues with scheduled jobs that do not process to completion, or that process with errors, are not addressed or are not addressed appropriately in the control description column or as a common description or control description. And within this identified control segregate control to ControlObject1, ControlObjective2 and ControlObjective3 based on the description provided for controls. ControlObjective1 should include control activities which mention about Jobs are scheduled inaccurately.  ControlObjective2 should include control activities which mention about Access to the job scheduler is inappropriate. ControlObjective3 should include control activities which mention about Issues with scheduled jobs that do not process to completion, or that process with errors, are not addressed or are not addressed appropriately.Do not provide any further explanation. Please provide the information in a JSON format compliant with RFC8259. JSON response should follow this format without deviation:"
        + "\n"
        + """[
        {
            "ControlsExists": "Indicate 'Yes' if relevant content related to job activities are included in the SOC report, otherwise 'No'.",
            "ControlObjective1": "ControlObjective1 Number, This is the unique identifier for the control activity related to jobs or job scheduling or automated job. If more control activities found, then provide a comma-separated string control objective numbers along with page number (e.g.,3.3 (page#30), 3.2(page#31), etc.). If not found return 'Not found'.",
            "ControlObjective2": "ControlObjective2 Number, This is the unique identifier for the control activity specific to the access for job scheduling or monitoring. If more control activities found, then provide a comma-separated string control objective numbers along with page number (e.g.,3.3 (page#30), 3.2(page#31), etc.). If not found return 'Not found'.",
            "ControlObjective3": "ControlObjective3 Number, This is the unique identifier for the control activity related to Issues with scheduled jobs that do not process to completion, or that process with errors, are not addressed or are not addressed appropriately. If more control activities found, then provide a comma-separated string control objective numbers along with page number (e.g.,3.3 (page#30), 3.2(page#31), etc.). If not found return 'Not found'."",
        }
    ]      
    Exclusion: Avoid listing control objectives with generic descriptions that contain no specific details about job scheduling, access to job scheduler and issues in scheduled jobs.
    """
     + "\n"
    )

    result = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(10),
        session_state=None,
        search_client_message="Controls which are specific to job scheduling, job monitoring and scheduling task inaccurate and so on",
        sourcefile=blob_name,
        section="section eq 'section 3 and section 4'",
        query_type=QueryType.FULL,
        addDefaultMessage=False
    )
    print(result)
    controlexists = 'No'
    controlObjectives1 = ''
    controlObjectives2 = ''
    controlObjectives3 = ''
    refPageNo = ''
    i = 0
    if processPageRange != None and len(processPageRange) > 0:
       if processPageRange[0].get("Job") != '':
            refPageNo = processPageRange[0].get("Job")
    for row in result:

            if row.get("ControlObjective1") != 'Not found' or \
              row.get("ControlObjective2") != 'Not found' or \
              row.get("ControlObjective3") != 'Not found':
              controlexists = 'Yes'
            
            controlObjectives1 = controlObjectives1  + ((',' if i != 0 else '') + str(row["ControlObjective1"] ) if row["ControlObjective1"] != 'Not found' else '')
            controlObjectives2 = controlObjectives2 + ((',' if i != 0 else '') + str(row["ControlObjective2"]) if row["ControlObjective1"] != 'Not found' else '')
            controlObjectives3 = controlObjectives3 + ((',' if i != 0 else '') + str(row["ControlObjective3"]) if row["ControlObjective1"] != 'Not found' else '')
            i = i+1
            
    columns = []
    columns.extend([
            {
                "ColumnKey": "tag_IT_jobMonitoringProcess_tbl_has_control_objectives_defined",
                "ColumnValue": controlexists,
                "ConfidenceScore": "0",
                "BoundingAreas": ""
            },
            {
                "ColumnKey": "tag_IT_jobMonitoringProcess_tbl_referenceWorkpaper",
                "ColumnValue": "",
                "ConfidenceScore": "0",
                "BoundingAreas": ""
            },
            {
                "ColumnKey": "tag_IT_jobMonitoringProcess_tbl_referencePageNo",
                "ColumnValue": refPageNo,
                "ConfidenceScore": "0",
                "BoundingAreas": ""
            },
            {
                "ColumnKey": "tag_IT_jobMonitoringProcess_tbl_substantiveStrategy",
                "ColumnValue": "",
                "ConfidenceScore": "0",
                "BoundingAreas": ""
            },
            {
                "ColumnKey": "tag_IT_jobMonitoringProcess_tbl_SA5",
                "ColumnValue": "",
                "ConfidenceScore": "0",
                "BoundingAreas": ""
            },
            {
                "ColumnKey": "tag_IT_jobMonitoringProcess_tbl_SA6",
                "ColumnValue": "",
                "ConfidenceScore": "0",
                "BoundingAreas": ""
            },
            {
                "ColumnKey": "tag_IT_jobMonitoringProcess_tbl_controlsReliance",
                "ColumnValue": "",
                "ConfidenceScore": "0",
                "BoundingAreas": ""
            },
            {
                "ColumnKey": "tag_IT_jobMonitoringProcess_tbl_CR6",
                "ColumnValue": controlObjectives1,
                "ConfidenceScore": "0",
                "BoundingAreas": ""
            },
            {
                "ColumnKey": "tag_IT_jobMonitoringProcess_tbl_CR7",
                "ColumnValue": controlObjectives2,
                "ConfidenceScore": "0",
                "BoundingAreas": ""
            },
            {
                "ColumnKey": "tag_IT_jobMonitoringProcess_tbl_CR8",
                "ColumnValue": controlObjectives3,
                "ConfidenceScore": "0",
                "BoundingAreas": ""
            }
        ])
    return columns

async def getItApps(
    approach: RetrieveThenReadApproach,blob_name: str,reportName: str
) -> dict:
    rows = []
    prompt_part1="""Please review the content of SOC( System and Organization Controls) Report in the following key 'Sources:' and identify the information that pertains to specific applications in scope or systems in scope or platforms in scope or operating systems in scope or databases in scope used by the service organization for which the SOC report is created. Strictly consider the conditions in tag \'Exclusion\': and \'Inclusion'.
            Inclusion: Please specifically not include sentences with following types of information:
            1 Include operating systems like Windows, Unix, Linux, Z/OS etc if any of the applications are hosted on them.
            2 Include databases like Oracle, SQL Server, DB2, MySQL etc if any of the applications use them to store data.
            3 If applications are listed in a table, include the 'Application Name' from the table
            4 If operating system is listed in a table, include the 'Operating System Technology' from the table
            5 if databases are listed in a table, include the 'Database Technology' from the table
            If no result found return empty array.
            For each relevant item, provide the following information in a JSON format:

        - Name: The name of the applications in scope or systems in scope or platforms in scope.
        - Description: The exact description of the application. if no description found return empty string.
        - Operating System: The operating system used by the application. if no operating system found return 'Not Found' as the value in the json  property 'Operating System'.
        - Database: The database used by the application. if no database found return 'Not Found'.
        - Confidence Score: A numeric score between 0.00 and 1.00 reflecting certainty about the accuracy of the information.
        - PageNo: The page number in the SOC 1 report where the information is found.

        Ensure that the response is formatted as a valid JSON array of objects adhering to the RFC8259 specification. Here is the structure to follow:

        [
        {
            "Name": "",
            "Description": "",
            "Operating System": "Return 'Not Found' if no operating system found",
            "Database": "Return 'Not Found' if no database found",
            "Confidence Score": "",
            "PageNo": ""
        }
        ]   """ 
    prompt= prompt_part1 
    exclusion=f"""Exclusion: Please specifically not include sentences with following types of information:
            1 Name of programming languages, protocols, or technologies such as Java, SQL, HTTPS, XML/HTTPS, SFTP, etc.
            2 All softwares or applications which part of different subservice organization.
            2 Do not pick data from any table which has column title like Subservice organization
            3 Do not pick data from Complimentary Subservice Organization Control
            4 Do not pick data from Subservice Organizations"""
            
    generictext1 =   f""" Section: Please specifically do not pick data from these sections:
    1. data from Control Activity
    2. data from Components of the system
    3. data from Complimentary Subservice Organization Control
    4. data from statements which don't have mention about services provided value"""
    data = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(20),
        session_state=None,
        search_client_message="applications in scope or systems in scope or platforms in scope",
        sourcefile=blob_name,
        addDefaultMessage=False,
        query_type=QueryType.SEMANTIC,
        section="section eq 'Section 3'",
        exclusionCriteria=exclusion
    )
    
    if data != None and len(data) > 1:
        usercontent = 'From the given objects in tag Sources:, select unique ones after removing duplicates by comparing similar names in Name field, and only include real Software applications or tools or OS, not any programming language, protocols, organizations etc.\nDo not include any explanations, only provide a RFC8259 compliant JSON response'
        startindex = 0
        result = []
        while startindex < len(data):
            resultdata = await approach.remove_duplicates(data[startindex:startindex+10],usercontent)
            startindex = startindex+10
            result.extend(resultdata)
    else:
        result = data
    apps = []
    for app in result:
        name = app["Name"]
        if len(name.strip()) == 0:
            continue
        if name not in apps:
            apps.append(name)
        else:
            continue
        columns = []
        try: 
            description = list(filter(lambda x: x["Name"] == name, data))[0]["Description"]
        except Exception as e:
            logging.error(e)
            description = ""
       
            
        columns.append(
            {
                "ColumnKey": "tag_IT_applications_tbl_applicationName",
                "ColumnValue": app["Name"],
                "ConfidenceScore": "0",
                "PageNo": 0,
                "BoundingAreas": "",
            }
        )
        columns.append(
            {
                "ColumnKey": "tag_IT_applications_tbl_applicationDescription",
                "ColumnValue": description,
                "ConfidenceScore": "0",
                "PageNo": 0,
                "BoundingAreas": "",
            }
        )
        rows.append({"PredictedColumns": columns})
        
        operatingSystem = app["Operating System"] if "Operating System" in app else ""
        database = app["Database"] if "Database" in app else ""
        if len(operatingSystem.strip()) == 0 and len(database.strip()) == 0:
            continue
        if operatingSystem == "Not Found" and database == "Not Found":
            continue
        columns=[]
        if operatingSystem not in apps and operatingSystem != "Not Found":
            apps.append(operatingSystem)
            columns.append(
                {
                    "ColumnKey": "tag_IT_applications_tbl_applicationName",
                    "ColumnValue": operatingSystem,
                    "ConfidenceScore": "0",
                    "PageNo": 0,
                    "BoundingAreas": "",
                }
            )
            columns.append(
                {
                    "ColumnKey": "tag_IT_applications_tbl_applicationDescription",
                    "ColumnValue": "Operating System",
                    "ConfidenceScore": "0",
                    "PageNo": 0,
                    "BoundingAreas": "",
                }
            )
            rows.append({"PredictedColumns": columns})
        
        columns=[]
        if database not in apps and database != "Not Found":
            apps.append(database)
            columns.append(
                {
                    "ColumnKey": "tag_IT_applications_tbl_applicationName",
                    "ColumnValue": database,
                    "ConfidenceScore": "0",
                    "PageNo": 0,
                    "BoundingAreas": "",
                }
            )
            columns.append(
                {
                    "ColumnKey": "tag_IT_applications_tbl_applicationDescription",
                    "ColumnValue": "Database",
                    "ConfidenceScore": "0",
                    "PageNo": 0,
                    "BoundingAreas": "",
                }
            )
            rows.append({"PredictedColumns": columns})
            
            
        
    return {"Name": "tag_IT_applications_tbl", "PredictedRows": rows}   

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
        reportname = msg_body.get("report_name", "")
        approach = await setup_clients()
        isItgcCarvedOut=await IsITGeneralControlsCarvedOut(approach, blob_name,reportname)
        if isItgcCarvedOut!=None and len(isItgcCarvedOut) > 0 and isItgcCarvedOut[0]['IsItgcCarvedOutCompletely'] == False:
            processPageRange=await GetProcessPageRange(approach, blob_name)
            itAppsTableData = await getItApps(approach, blob_name, reportname)
            logging.error("itapps");
            changeProcessControls = await GetChangeProcessControls(approach, blob_name,processPageRange)
            trows = []
            logging.error("changeProcessControls");
            trows.extend([{"PredictedColumns": changeProcessControls}] * len(itAppsTableData['PredictedRows']))
            chanProceCntrlsTable = {"name":'tag_IT_changeProcess_tbl',"PredictedRows": trows}
            
            accessProcessControls = await GetAccessProcessControls(approach, blob_name,processPageRange)
            logging.error("accessProcessControls");
            trows1 = []
            trows1.extend([{"PredictedColumns": accessProcessControls}] * len(itAppsTableData['PredictedRows']))
            accessProcessControlsTable = {"name":'tag_IT_accessProcess_tbl',"PredictedRows": trows1}

            jobMonitorControls = await GetJobMonitorControls(approach, blob_name,processPageRange)
            trows3 = []
            trows3.extend([{"PredictedColumns": jobMonitorControls}] * len(itAppsTableData['PredictedRows']))
            jobMonitorControlTable = {"name":'tag_IT_jobMonitoringProcess_tbl',"PredictedRows":trows3}

            #Constructing data to send to API
            result_data = {"TableEntities":[itAppsTableData,chanProceCntrlsTable,accessProcessControlsTable,jobMonitorControlTable],"Entities":""}
        else:
            result_data = {"TableEntities":[],"Entities":""}     
        
        json_string = json.dumps(result_data)
        # print (json_string)
        logging.error('going to call api')
        logging.error(json_string)
        data = {
                "documentId": blob_id,
                "extractedTagValues": json_string,
                "blobFilePath": "",
                "predictionBlobPath": "",
                "errorMessage": "",
                "sectionName":"IT apps, IT processes & ITGCs",
                "CorrelationId": CorrelationId
        }
        data_json = json.dumps(data)
        logging.error(data_json)
        response = ApiManager().callback_api(data_json)
        logging.error(response)
    except Exception as e:
        documentName = blob_name.split('/')[-1]
        LogError(e, e,CorrelationId,blob_id,documentName)

