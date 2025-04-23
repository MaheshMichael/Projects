import json
import logging
import os
from azure.functions import QueueMessage
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from core.logger import LogError
from prepdocslib.apimanager import ApiManager
from prepdocslib.searchmanager import Section
from secrets_manager import SecretsManager
from openai import AsyncOpenAI
from ..data_retrieval_rag_openai.retrievethenread import RetrieveThenReadApproach
from azure.search.documents.models import (
    QueryType
)
def socname_question():
    return """[
        {
            "Name": "Subservice organization (SSO) name, if short name is used then provide the full name if found, and use the name exactly as it appears in the tag 'Sources:'",
            "ShortName":"Name of Subservice organization",
            "Confidence Score": "Confidence score of the result in double",
            "PageNo": "Page Number from Source content",
        }
    ]"""
def subserviceinfo_question():
    return """[
        {
            "Name": ["List of Subservice organization (SSO) names and use the name exactly as it appears in the tag 'Sources:'. If no mention about subservice organizations, return 'Not found'"],
            "Service Provided":["List of services used by subservice organizations, return 'Not found' if no mention about services used"],
            "Confidence Score": "Confidence score of the result in double",
            "PageNo": "Page Number from Source content",
        }
    ]"""
def subserviceName_question():
    return """[
        {
            "Name": "Subservice organization (SSO) name and use the name exactly as it appears in the tag 'Sources:'. If no mention about subservice organizations, return 'Not found'"],
            "ShortName":"Name of Subservice organization",
            "Confidence Score": "Confidence score of the result in double",
            "PageNo": "Page Number from Source content",
        }
    ]"""
def isInclusiveOrCarveOutQuestion(orgName):
    return """[
        {
            "IsInclusive": "state clearly whether the subservice organization, """ + orgName + """ is treated using the Inclusive or Carved Out method based on the evidence in the SOC 1 report. if not found return 'Not found'",
            "Confidence Score": "Confidence score of the result in double",
            "PageNo": "Page Number from Source content",
        }
    ]"""
        
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
    prompt_base_template = "You are an auditor reviewing the section subservice organizations that are mentioned in the SOC 1 report and need to answer questions based on the text provided in key Source:. A subservice organization in a SOC 1 report is a third-party entity that is used by the service organization to perform some of the services provided to user entities. These services are likely to be relevant to the internal control over financial reporting of the user entities."
    return RetrieveThenReadApproach(
        search_client=search_client,
        openai_client=openai_client,
        openai_chatgpt_model="gpt-4-32k",
        chatgpt_model="gpt-4-32k",
        chatgpt_deployment="chat",
        embedding_model="text-embedding-ada-002",
        embedding_deployment="text-embedding-ada-002",
        sourcepage_field="sourcepage",
        content_field="content",
        query_language="en-us",
        query_speller="lexicon",
        openai_temprature=0,
        main_prompt_template=prompt_base_template,
        openai_batch_size=20,
        openai_max_tokens=5000


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
def service_provided_question(orgName):
    prompt = (
            '[{"Service Provided": "Retrieve the relevant portion of text relates to the specific description of only the services provided by '
            + orgName
            + ' a subservice organization to the entity. If not found return \'Not Found\'", "PageNo": "Page Number from Source content"}]'
        )
    return prompt
async def isSubserviceOrga_inclusiveOrCarveOut(approach,orgName,blob_name):
    generictext = """Please analyze the attached SOC 1 report and provide a summary on how the subservice organization {orgName} is treated. Specifically, look for the following information and consider this in your analysis:
    Service Organization's System Description:
    Indicate whether the system description includes controls related to the subservice organization, which would suggest an inclusive method.
    If the system description acknowledges the subservice organization's functions but excludes them from the control description, this would suggest a carve-out method.
    Scope of the Audit:
    Highlight any statements in the audit scope that clarify whether the subservice organization's controls are included in or excluded from the audit.
    Auditor's Opinion:
    Provide excerpts from the auditor's opinion that reveal whether the subservice organization was or was not part of the audit, indicating the approach used.
    Control Objectives and Control Activities:
    Identify whether the report includes specific control objectives and activities that relate to the subservice organization, pointing towards an inclusive method.
    If the report mentions such activities as being outside the scope, note it as an indication of the carve-out method.
    Supplementary Information:
    Check for any sections that offer additional clarification on the role and responsibilities of the subservice organization in relation to the service organization's internal control over financial reporting.
    User Control Considerations:
    Look for areas in the report where there are user control considerations or instructions for the user entity, specifically pertaining to the involvement of a subservice organization."""
    template = generictext + " Do not include any explanations, \
        only provide a RFC8259 compliant JSON response following this \
        format without deviation Format : "
    orgserviceprompt = (
            template + "\n" + isInclusiveOrCarveOutQuestion(orgName) + "\n"
        )
    result = await approach.run(
            [{"content": orgserviceprompt}],
            # [{"content":"what i}s the entity name from report EY Global CTP SOC 2 Type 2 Report 2022.pdf","role":"user"}],
            stream=True,
            context=getContext(5),
            session_state=None,
            search_client_message="Subservice organization's controls or Carve-out method or Excluded from the audit scope or User Control Considerations for subservice organizations or desscription of the system or scope of the audit or Auditor's opinion on subservice organization or Inclusive in the description of the system" ,
            sourcefile=blob_name,
            section = "(section eq 'Section 1' or section eq 'Section 2' or section eq 'Section 0')"
        )
        # result = json.loads(answer['content'])
    if isinstance(result, list):
            if len(result) > 0:
                return {
                    "ColumnKey": "tag_subserviceOrganizations_tbl_carved_inclusive",
                    "ColumnValue": result[0]["IsInclusive"],
                    "ConfidenceScore": "0",
                    "PageNo": result[0]["PageNo"] if isinstance(result[0]["PageNo"], int) else 0,
                    "BoundingAreas": "",
                }
    return None
async def order_services_provided(approach,orgName,blob_name,serviceProvided):
    genericText = f"""We are analyzing a SOC 1 report and the aim is to find the services provided by the 
    subservice organization,{orgName}. We alreay fetched the results after analyzing the SOC report in an array as mentioned in tag 'Source:' . 
    You need to order the results based on the specificity and clarity of the statements mentioning the specific services and with statements mentioning the type of service taking precedence. 
    If a specific description is not found, provide a generic description which indicates the services providing by Subservice organization. Order the results based on the relevance of the specific services utilized by the service organization with the most directly relevant specific service provided by {orgName} listed first. 
    Do not include any explanations, only provide a RFC8259 compliant JSON response following this format without deviation 
    Format : """+ '{"Service Provided": "Service provided by the subservice organization","PageNo": "Page Number from Source content"}'
    result  = await approach.openai_only_prompt(serviceProvided,genericText)
    return result
async def service_Provided_from_auditorsreport(approach,orgName,blob_name):
    generictext = "the specific description of only the services provided by the sub-service organization, '" + orgName + "' excluding any information about controls or scope details as stated in the source text. If a specific description is not found, summerize the service provided value after reading the content in source text. Order the results based on Confidence Score and Page Number and order based on the relevance of the services utilized by the service organization with the most directly relevant service provided by {orgName} listed first. There are scenarios where there will be a table for 'Subservice Organizations' in the SOC report, then only pick the data from that table because it will be the most relevant result and make sure it should come first in the result "
    template = "The aim is to find " + generictext  + " Do not include any explanations, only provide a RFC8259 compliant \
            JSON response following this format without deviation Format : "
    orgserviceprompt = (
            template + "\n" + service_provided_question(orgName) + "\n"
    )
    result = await approach.run(
            [{"content": orgserviceprompt}],
            # [{"content":"what i}s the entity name from report EY Global CTP SOC 2 Type 2 Report 2022.pdf","role":"user"}],
            stream=True,
            context=getContext(5),
            session_state=None,
            search_client_message="Independent Service Auditor's Report",
            sourcefile=blob_name,
            query_type=QueryType.SEMANTIC,
            fetchExtra=True
        )
    result = [res for res in result if res.get("Service Provided") != "Not Found"]
    return result

    # generictext = (
    #         "The exact description of services provided by
async def service_Provided(approach,orgName,blob_name,serviceProvided):
    generictext = "the specific description of only the services provided by the sub-service organization, " + orgName +' excluding any other information about controls or scope details as stated in the source text and strictly consider the conditions in tag \'Exclusion\': and conditions in tag \'Section\': and conditions in tag \'Inclusion\': and conditions in tag \'Order\': . Please include information on any key responsibilities and operations '+ orgName + ' undertakes that are significant to the service organization\'s system and security considerations. This should include any critical applications they host, the type of hosting services they provide(such as cloud hosting), and any other functions they perform that are relevant to the service organization\'s internal control over financial reporting. Order the results based on Confidence Score and Page Number and order based on the relevance of the services utilized by the service organization with the most directly relevant service provided by {orgName} listed first. ' 
    exclusion = f"""Exclusion: Please specifically not include sentences with following types of information:
    1 Details about control objectives
    2 Details about monitoring controls
    3 Do not pick statements about 'Controls' and scope details
    4 Do not pick just the Application name instead of service provided value
    5 Details about Control Description
    6 Details about Control Groupings
    7 Application or Organization Description
    8 Details from control activities
    9 Do not pick data from Control Activity
    10 Do not pick data from Components of the system
    11 Do not pick data from statements which don't have mention about services provided value
    12 Do not pick data from Complimentary Subservice Organization Control
    13 Do not pick data if there is a text like 'Expected Complementary Subservice Organization Control(s)' in that page
    14 Details from control activities that do not directly relate to the services provided by """ + orgName
    generictext1 =   f""" Section: Please specifically do not pick data from these sections:
    1. data from Control Activity
    2. data from Components of the system
    3. data from Complimentary Subservice Organization Control
    4. data from statements which don't have mention about services provided value"""
    generictext1 = generictext1 + f""" Order: There are scenarios where there will be a table for 'Subservice Organizations' in the SOC report, then only pick the data from that table because it will be the most relevant result and make sure it should come first in the result """
    rerunquery = True
    template = ''
    if serviceProvided and len(serviceProvided) > 0:
        result = await service_Provided_from_auditorsreport(approach,orgName,blob_name)
        if result == None or len(result)== 0:
            rerunquery = True
            service = ''.join([str(word) for word in serviceProvided])
            generictext1 = generictext1 + f""" Inclusion: Only include services which relates to these list of services, ###{service}###"""
            format1 = f""" Do not include any explanations, only provide a RFC8259 compliant JSON response following this format without deviation. If no result found return empty array. Begin your response with """
            template = "The aim is to find " + generictext + generictext1 + format1
        else:
            rerunquery = False
    else:
        rerunquery = True
        service = ''.join([str(word) for word in serviceProvided])
        generictext1 = generictext1 + f""" Inclusion: Only include services which relates to these list of services, ###{serviceProvided}###"""
        format1 = f""" Do not include any explanations, only provide a RFC8259 compliant JSON response following this format without deviation. If no result found return empty array. Begin your response with """
        template = "The aim is to find " + generictext + generictext1 + format1
    # generictext = (
    #         "The exact description of services provided by the sub-service organization, "
    #         + orgName
    #         + ", based on Confidence Score and Page Number. Please use the exact text from the tag 'Sources': including information on any key responsibilities and operations they undertake that are significant to the service organization's system and security considerations. This should include any critical applications they host, control environments they manage, specific controls they implement, and any other functions they perform that are relevant to the service organization's internal control over financial reporting."
    #     )
    if rerunquery:
        orgserviceprompt = (
            template + "\n" + service_provided_question(orgName) + "\n"
        )
        result = await approach.run(
            [{"content": orgserviceprompt}],
            # [{"content":"what i}s the entity name from report EY Global CTP SOC 2 Type 2 Report 2022.pdf","role":"user"}],
            stream=True,
            context=getContext(10),
            session_state=None,
            search_client_message="Services provided by Subservice organization ,'" + orgName +"'",
            sourcefile=blob_name,
            query_type=QueryType.SEMANTIC,
            exclusionCriteria=exclusion
            
        )
   # result = await order_services_provided(approach,orgName,blob_name,result)
        # result = json.loads(answer['content'])
    if isinstance(result, list):
            if len(result) > 0:
                if result[0]["Service Provided"] == "Not Found":
                    return None
                else:
                    return {
                        "ColumnKey": "tag_subserviceOrganizations_tbl_scomponents",
                        "ColumnValue": result[0]["Service Provided"],
                        "ConfidenceScore": "0",
                        "PageNo": result[0]["PageNo"] if isinstance(result[0]["PageNo"], int) else 0,
                        "BoundingAreas": "",
                    }
    return None


async def getSubserviceOrganizations(
    approach: RetrieveThenReadApproach,blob_name: str,reportName: str,
    subservices: list,servicesProvided: list
) -> dict:
    rows = []
    # format1 =  "Please identify external subservice organizations including any independent entities that are not part of " + reportName + " that it outsources some of its tasks of functions to.\
    # Specifically, look for internal groups that operate with functional independence, have their own service auditor's reports, and whose services are relevant to the internal control over financial reporting of the user entities, as well as entities providing physical infrastructure services.\
    # Do not include internal teams or divisions of the service organization, entities that are part of the service organization, or any other internal services.\
    # Exclude any third parties, vendors, products, services, internal departments, roles, offices, roles or occupation titles within " + reportName + '.'
    format = f""" Identify external subservice organization names mentioned in the SOC 1 report, and strictly consider the conditions in tag 'Exclusion': .
    A subservice organization can also be an internal group within the entity that supports specific operations or systems.
    Include entities or organization names that are explicitly identified as subservice organizations or complementary subservice organizations as well as entities that provide underlying system support, infrastructure or data center support that is critical to the service organization's service delivery. 
    Provide information only from explicit statements in the SOC 1 report; do not infer or assume entities are subservice organizations based on their mention alone.
    Include Subservice organizations from table if it has columns like subservice organization and services provided and the text in the table is relevant to the subservice organization and no mention like not a subservice organization in the table. Following are the exclusion criteria:
    Exclusion: 1. Exclude primary entity ie {reportName} or the subject of the report.
    2. Exclude  the primary entity, parent organization, or service organization that is the subject of the SOC report from your findings. But If the primary entity is directly mentioned in the subservice organization table, include it in the findings
    3. Exclude generic names like ex:- "Application Service provider or Hosting provider"
    """
    if subservices and len(subservices) > 0:
        service = ''.join([str(word) for word in subservices])
        format = format + f"""4. Include organizations with same name or names related to : ' {service} '
    """
    if servicesProvided and len(servicesProvided) > 0:
        servicesprovided = ','.join([str(word) for word in servicesProvided])
        format = format + f"""5. Only include subservice organizations that provide services like : {servicesprovided}"""
    format1 = f"""Do not include any explanations, only provide a RFC8259 compliant JSON response following this format without deviation. If no result found return empty array. Begin your response with """
    prompt = format  + format1 + "\n" + socname_question() + "\n"
    data = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(10),
        session_state=None,
        search_client_message="Subservice organization",
        sourcefile=blob_name,
        addDefaultMessage=False,
        query_type=QueryType.FULL
        # section="(section eq 'Section 3')"
    )
    if ((data == None or len(data)==0) and (subservices != None and len(subservices) > 0)):
        data = await getServiceOrganizationsFromAuditorsReport(approach,blob_name,reportName)
    if data != None and len(data) > 1:
        result = await approach.remove_duplicates(data)
    else:
        result = data
    orgs = []
    for org in result:
        name = org["Name"] if len(org["ShortName"]) == 0 else org["ShortName"]
        if len(name.strip()) == 0:
            continue
        if name not in orgs:
            orgs.append(name)
        else:
            continue
        column = await service_Provided(approach,org["Name"],blob_name,servicesProvided)
        if column != None:
            columns = []
            columns.append(
                {
                    "ColumnKey": "tag_subserviceOrganizations_tbl_ssoname",
                    "ColumnValue": org["Name"] + "(PageNo#" + str(org["PageNo"]) + ")",
                    "ConfidenceScore": "0",
                    "PageNo": org["PageNo"] if isinstance(org["PageNo"], int) else 0,
                    "BoundingAreas": "",
                }
            )
            columns.append(column)
            column = await isSubserviceOrga_inclusiveOrCarveOut(approach,name,blob_name)
            if column != None:
                columns.append(column)
            rows.append({"PredictedColumns": columns})
    return {"Name": "tag_subserviceOrganizations_tbl", "PredictedRows": rows}
async def getServiceOrganizationsFromAuditorsReport(approach: RetrieveThenReadApproach,blob_name: str,reportName: str) -> dict:
    format = f""" I need the names of the subservice organizations used by a specific entity {reportName} by analyzing the SOC report data mentioned in tag 'Source:'. A subservice organization can also be an internal group within the entity that supports specific operations or systems. Sometimes, the organization name may not be explicitly mentioned, and it's only stated that a subservice organization is used. In such cases, simply return "Subservice organization". In cases where the entity does not use any subservice organization, return "Not found" for both the name.
     If the specific type of service (e.g., cloud hosting services) is not mentioned, return "Not found" for "Service Provided".
    Do not include any explanations, only provide a RFC8259 compliant JSON response following this format without deviation and don't add any extra keys over json. If no result found return empty array. Begin your response with """
    prompt = format  +  subserviceName_question() + "\n"
    data = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(10),
        session_state=None,                             
        search_client_message="Independent Service Auditor's Report",
        addDefaultMessage=False,
        sourcefile=blob_name,
        query_type=QueryType.FULL
        # section="(section eq 'Section 3')"
    )
    data = [x for x in data if x["Name"] != "Not found" and x["Name"] != "Subservice organization"]
    return data

async def getSubserviceOrganizationsFromIndependentAuditorsReport(approach: RetrieveThenReadApproach,blob_name: str,reportName: str) -> dict:
    rows = []
    format = f""" I need the names of the subservice organizations used by a specific entity {reportName} and service provided by analyzing the SOC report data mentioned in tag 'Source:'. A subservice organization can also be an internal group within the entity that supports specific operations or systems. Sometimes, the organization name may not be explicitly mentioned, and it's only stated that a subservice organization is used. In such cases, simply return "Subservice organization". At times, it might be mentioned that certain services are being used from a subservice organization. In these instances, populate the "Service Provided" array. In cases where the entity does not use any subservice organization, return "Not found" for both the name and service provided keys.
     If the specific type of service (e.g., cloud hosting services) is not mentioned, return "Not found" for "Service Provided".
    Do not include any explanations, only provide a RFC8259 compliant JSON response following this format without deviation and don't add any extra keys over json. If no result found return empty array. Begin your response with """
    prompt = format  +  subserviceinfo_question() + "\n"
    data = await approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(10),
        session_state=None,                             
        search_client_message="Independent Service Auditor's Report",
        addDefaultMessage=False,
        sourcefile=blob_name,
        query_type=QueryType.FULL
        # section="(section eq 'Section 3')"
    )
    print(data)
    #Get subservice organizations, service provided and check if there is organization is empty
    #Scenario 1: If organization is empty and service provided is empty then return empty array
    try:
        if data == None or len(data) == 0:
            return {"SubServiceOrgs" : [] , "ServiceProvided" : [],"IsSubServiceOrgPresent":False}
        elif len(data)> 0:
            subservices = []
            isSubServicePresent = False
            serviceProvided = []
            for org in data:
                if isinstance(org["Name"],list):
                    for suborg in org["Name"]:
                        if suborg != "Not found" and suborg != "Subservice organization":
                            subservices.append(suborg)
                            isSubServicePresent = True
                        if suborg == "Subservice organization":
                            isSubServicePresent = True
                else:  
                    if org["Name"] != "Not found" and org["Name"] != "Subservice organization":
                        subservices.append(org["Name"])
                        isSubServicePresent = True
                    if org["Name"] == "Subservice organization":
                        isSubServicePresent = True
                if isinstance(org["Service Provided"],list):
                    for service in org["Service Provided"]:
                        if service != "Not found":
                            serviceProvided.append(service)
                            isSubServicePresent = True
                else:
                    if org["Service Provided"] != "Not found":
                        serviceProvided.extend(org["Service Provided"])
                        isSubServicePresent = True
                
            return {"SubServiceOrgs" : subservices , "ServiceProvided" : serviceProvided,"IsSubServiceOrgPresent":isSubServicePresent} 
    except Exception as e:
        print(e)
        return {"SubServiceOrgs" : [] , "ServiceProvided" : [],"IsSubServiceOrgPresent":True}
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
        data = await getSubserviceOrganizationsFromIndependentAuditorsReport(approach,blob_name,reportname)
        isSubServiceOrgPresent = data.get("IsSubServiceOrgPresent")
        if isSubServiceOrgPresent == True:
            subServices = data.get("SubServiceOrgs")
            servicesProvided = data.get("ServiceProvided")
            tableData = await getSubserviceOrganizations(approach, blob_name, reportname,subServices,servicesProvided)
            isSubServiceOrgPresent = True
            if tableData and len(tableData.get("PredictedRows")) > 0:
                isSubServiceOrgPresent = False
        else:
            tableData = {"Name": "tag_subserviceOrganizations_tbl", "PredictedRows": []}
        entitiesData = []
        entitiesData.append(
            {
                "Name": "tag_subserviceOrganizations_noSubserviceOrganizations",
                "PredictedValues":[{"Value":isSubServiceOrgPresent,"ConfidenceScore":"0","PageNo":0}]
            })

        result_data = {"TableEntities":[tableData],"Entities":entitiesData}
        json_string = json.dumps(result_data)
        logging.error('going to call api')
        logging.error('jsonstring ',result_data)
        data = {
                "documentId": blob_id,
                "extractedTagValues": json_string,
                "blobFilePath": "",
                "predictionBlobPath": "",
                "errorMessage": "",
                "sectionName":"Subservice organizations",
                "CorrelationId": CorrelationId
        }
        data_json = json.dumps(data)
        logging.error(data_json)
        response = ApiManager().callback_api(data_json)
        logging.error(response)
    except Exception as e:
        documentName = blob_name.split('/')[-1]
        LogError(e, e,CorrelationId,blob_id,documentName)
