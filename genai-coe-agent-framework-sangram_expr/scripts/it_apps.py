import os
import json

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import QueryType

from utils.retrievethenread import RetrieveThenReadApproach

# report_name = os.environ["REPORT_NAME"]


def setup_clients():
    import openai

    # Set up clients for AI Search and Storage
    [aisearch_index_name, aisearch_endpoint, aisearch_key] = (
        os.environ["AZURE_SEARCH_INDEX_NAME"],
        os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"],
        os.environ["AZURE_SEARCH_API_KEY"],
    )
    search_client = SearchClient(
        endpoint=aisearch_endpoint,
        index_name=aisearch_index_name,
        credential=AzureKeyCredential(aisearch_key),
    )
    [openaiendpoint, openaikey, organization] = (
        os.environ["AZURE_OPENAI_ENDPOINT"],
        os.environ["AZURE_OPENAI_API_KEY"],
        os.environ["AZURE_OPENAI_SERVICE_NAME"],
    )

    openai_client = openai.AzureOpenAI(
        azure_endpoint=openaiendpoint,
        api_key=openaikey,
        api_version="2023-03-15-preview",
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
        openai_max_tokens=20000,
    )


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


def IsITGeneralControlsCarvedOut(
    approach: RetrieveThenReadApproach, report_name: str
) -> dict:
    rows = []
    base = f""" Identify the area which mentions about 'Information Technology General Controls' or 'ITGC' in the SOC report specifically mentioned under the heading 'Description of {report_name}' . Then look for specific statements says Scope of 'ITGC' or 'Information Technology General Controls' or 'IT infrastructure support' and see if those are carved out or handled or provide as part of another subservice organization. Information Technolgy controls are the controls which manage processes like like  logical access, change management, job scheduling, incident, problem management, backup data and physical access which are basically the IT processes or controls tested in the SOC report. A subservice organization can also be an internal group within the entity that supports specific operations or systems.In some cases,not all these process are handled or completely carved out in a separate report or managed by a different subservice organization. Return true for below property 'IsItgcCarvedOutCompletely' only if all of them are carved out. If in case some processes are still managed in this report currently being audited, then return as false. Do not include any explanations, only provide a RFC8259 compliant JSON response following this format without deviation.  """
    format = """ Format :
                {
                    "IsItgcCarvedOutCompletely": "Boolean value to specify if the scope of 'Information Technology General Controls' or 'ITGC' are carved out or 'ITGC' or 'Information Technology General Controls' or 'IT infrastructure support' and see if those are carved out or handled or provide as part of another subservice organization. Set this as true if it is handled  or carved out or mentioned as part of another subservice organization, otherwise set this as false.",
                }"""

    prompt = base + "\n" + format
    data = approach.run(
        [{"content": prompt}],
        stream=True,
        context=getContext(10),
        session_state=None,
        search_client_message="Scope of this Report or ITGC or Information Technology General Controls or Infrastructure Controls or Service Provided",
        addDefaultMessage=True,
        sourcefile=report_name,
        query_type=QueryType.SEMANTIC,
        # section="(section eq 'Section 3')"
    )
    print(data)
    # Get subservice organizations, service provided and check if there is organization is empty
    # Scenario 1: If organization is empty and service provided is empty then return empty array
    try:
        if data == None or len(data) == 0:
            return {"IsItgcCarvedOutCompletely": ""}
        else:
            return data
    except Exception as e:
        print(e)
        return {"IsItgcCarvedOutCompletely": False}


def getItApps(approach: RetrieveThenReadApproach, report_name: str) -> dict:
    rows = []
    prompt_part1 = """Please review the content of SOC( System and Organization Controls) Report in the following key 'Sources:' and identify the information that pertains to specific applications in scope or systems in scope or platforms in scope or operating systems in scope or databases in scope used by the service organization for which the SOC report is created. Strictly consider the conditions in tag \'Exclusion\': and \'Inclusion'.
            Inclusion: Please specifically include sentences with following types of information:
            1 If applications are listed in a table, include the 'Application Name' and 'Description' from the table. Exclude the 'Application Name' and 'Description' from the table is they are subclassified as Databases or connectors or other infrastructure components.
            2 If applications are founded in text or paragraphs, include the 'Application Name' and 'Description' from the text.
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
    prompt = prompt_part1
    exclusion = f"""Exclusion: Please specifically not include sentences with following types of information:
            1 Name of programming languages, protocols, or technologies such as Java, SQL, HTTPS, XML/HTTPS, SFTP, etc.
            2 All softwares or applications which part of different subservice organization.
            2 Do not pick data from any table which has column title like Subservice organization
            3 Do not pick data from Complimentary Subservice Organization Control
            4 Do not pick data from Subservice Organizations
            5 Do not pick Operating System and Database applications unless the report is generic and audits infrastructure of the organization
            6 Do not incude same applications and their description from text if they are already found in table"""

    generictext1 = f""" Section: Please specifically do not pick data from these sections:
    1. data from Control Activity
    2. data from Components of the system
    3. data from Complimentary Subservice Organization Control
    4. data from statements which don't have mention about services provided value"""
    data = approach.run(
        [{"content": prompt}],
        stream=False,  # Changed to synchronous
        context=getContext(20),
        session_state=None,
        search_client_message="applications in scope or systems in scope or platforms in scope",
        sourcefile=report_name,
        addDefaultMessage=False,
        query_type=QueryType.SEMANTIC,
        # section="section eq 'Section 3'",
        exclusionCriteria=exclusion,
    )

    if data is not None and len(data) > 1:
        usercontent = "From the given objects in tag Sources:, select unique ones after removing duplicates by comparing similar names in Name field, and only include real Software applications or tools or OS, not any programming language, protocols, organizations etc.\nDo not include any explanations, only provide a RFC8259 compliant JSON response"
        startindex = 0
        result = []
        while startindex < len(data):
            resultdata = approach.remove_duplicates(
                data[startindex : startindex + 10], usercontent
            )
            startindex += 10
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
            description = list(filter(lambda x: x["Name"] == name, data))[0][
                "Description"
            ]
        except Exception as e:
            print(str(e))
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
        columns = []
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

        columns = []
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


def data_writer(report_name, fname, output_folder, data):
    file_name = f"{report_name}-{fname}.txt"
    file_path = os.path.join(output_folder, file_name)

    with open(file_path, "w", encoding="utf-8") as output:
        output.write(json.dumps(data, indent=4))


if __name__ == "__main__":
    # Construct the output folders
    output_folder = os.path.join("data", "output")

    # Ensure the output folders exist
    os.makedirs(output_folder, exist_ok=True)

    approach = setup_clients()

    for report_file_name in os.listdir("data/reports"):
        if report_file_name.endswith(".xlsx"):
            report_name = os.path.splitext(report_file_name)[0]
            print(report_name)

            isItgcCarvedOut = IsITGeneralControlsCarvedOut(approach, report_name)
            print(isItgcCarvedOut)

            if (
                isItgcCarvedOut is not None
                and len(isItgcCarvedOut) > 0
                and not isItgcCarvedOut[0]["IsItgcCarvedOutCompletely"]
            ):
                itAppsTableData = getItApps(approach, report_name)

                result_data_apps = {"TableEntities": [itAppsTableData], "Entities": ""}

            else:
                # If ITGCs are carved out, return empty tables
                result_data_apps = {"TableEntities": [], "Entities": ""}

            data_apps = {
                "documentId": report_name,
                "extractedTagValues": result_data_apps,
                "blobFilePath": "",
                "predictionBlobPath": "",
                "errorMessage": "",
                "sectionName": "5. IT applications",
                "CorrelationId": report_name,
            }

            data_writer(report_name, "it-apps", output_folder, data_apps)
