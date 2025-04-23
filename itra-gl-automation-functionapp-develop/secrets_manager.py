from enum import Enum
import os
import stat
from typing import Tuple
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
class SecretsManager:
    load_dotenv(override=True)
    APIURL = os.environ["APIURL"]   
    DBStorageConnectionString = os.environ["TableStorageConnectionString"]
    DBName = os.environ["DBName"]
    DBSERVER = os.environ["DBSERVER"]
    DBUSER = os.environ["DBUSER"]
    DBPASSWORD = os.environ["DBPASSWORD"]
    AZURE_KEYVAULT_SECRET_NAME = "your-secret-name"
    SOC_DATA_STORAGE_ACCOUNT = os.environ["SOC_DOCUMENTS_BLOB_CONNECTION_STRING"]
    SOC_QUEUE_STORAGE_ACCOUNT = os.environ["SOC_DOCUMENTS_QUEUE_CONNECTION_STRING"]
    SOC_DATA_STORAGE_ACCOUNT_CONTAINER_NAME = os.environ["SOCR_DOCUMENTS_CONTAINER"]
    SOC_AI_SEARCH_ENDPOINT = os.environ['SOC_AI_SEARCH_ENDPOINT']
    SOC_AI_SEARCH_KEY = 'Vgd7lQ9p89LJLcKR5xvyV8qS8meWiFLaSYR5ViOLdKAzSeChhBSB'
    SOC_AI_SERACH_INDEX_NAME = os.environ["SOC_AI_SERACH_INDEX_NAME"]
    SOC_DOCUMENT_INTELLIGENCE_SERVICE_ENDPOINT = "https://uscdadvecnazai02.cognitiveservices.azure.com/"
    SOC_DOCUEMENT_INTELLIGENCE_SERVICE_KEY = '8f7a732cc0dd48bd85ad31ff8cbdb442'
    SOC_OPEN_AI_SERVICE_NAME = 'frccoai0ucaoa01'
    # SOC_OPEN_AI_DEPLOYMENT_NAME = 'text-embedding-ada-002'
    SOC_OPEN_AI_CHAT_DEPLOYMENT_NAME = 'gpt-4'
    SOC_OPEN_AI_MODEL_NAME = 'text-embedding-ada-002'
    SOC_OPEN_AI_MODEL_KEY = 'c70f812334a84461968005fa8eea060d'
    # SOC_DELTA_LAKE_STORAGE_ACCOUNT = f'https://DefaultEndpointsProtocol=https;AccountName={os.environ["SOC_STORAGE_ACCOUNT_NAME"]};AccountKey={os.environ["SOC_STORAGE_ACCOUNT_KEY"]};EndpointSuffix=core.windows.net.blob.core.windows.net'
    SOC_DELTA_LAKE_STORAGE_ACCOUNT = f'https://{os.environ["107glautomation_STORAGE"]}.blob.core.windows.net'
    SOC_DELTA_LAKE_STORAGE_ACCOUNT_KEY = '0y0JsbhfpO7ODpoema+6Q6EV4NmI8w1VYmi6xhMl5+NJNKSti1eQJbspkJhnUA1M4fxk/MYhckkk+AStfz8qcw=='
    GL_DATA_STORAGE_ACCOUNT_CONTAINER_NAME  = 'itra-socr-processed-docs'
    GL_DATA_TEMPLATE_NAME = 'template.json'
    class Queues(Enum):
        Retrievesocreport = "retrievesocreport"
    @staticmethod 
    def get_DocumentIntelligenceDetails() -> Tuple[str, str]:
        # SecretsManager.set_secret('GLAutomationDocIntelligenceEndpoint','https://uscdadvecnazai02.cognitiveservices.azure.com/')
        # SecretsManager.set_secret('GLAutomationDocIntelligenceKey','8f7a732cc0dd48bd85ad31ff8cbdb442')
        return "https://uscdadvecnazai02.cognitiveservices.azure.com/",'8f7a732cc0dd48bd85ad31ff8cbdb442'
        # return SecretsManager.read_secret('GLAutomationDocIntelligenceEndpoint'), SecretsManager.read_secret('GLAutomationDocIntelligenceKey')
    @staticmethod
    def get_openAiServiceDetails() -> Tuple[str,str]:

        return os.environ['SOC_OPEN_AI_SERVICE_NAME'],os.environ['SOC_OPEN_AI_DEPLOYMENT_NAME']
    @staticmethod
    def get_AISearchDetails() -> Tuple[str, str, str]:
        return SecretsManager.SOC_AI_SERACH_INDEX_NAME, os.environ['SOC_AI_SEARCH_ENDPOINT'], "Vgd7lQ9p89LJLcKR5xvyV8qS8meWiFLaSYR5ViOLdKAzSeChhBSB"
        # return SecretsManager.SOC_AI_SERACH_INDEX_NAME, os.environ['SOC_AI_SEARCH_ENDPOINT'], SecretsManager.read_secret("GLAutomationAISearchKey")
    @staticmethod
    def get_OpenAIDetails() -> Tuple[str, str]:
        # SecretsManager.set_secret('SOCOPENAIKEY','c70f812334a84461968005fa8eea060d')
        return os.environ['SOC_OPENAI_ENDPOINT'],'c70f812334a84461968005fa8eea060d',os.environ['SOC_OPEN_AI_SERVICE_NAME']
        # return os.environ['SOC_OPENAI_ENDPOINT'], SecretsManager.read_secret('GLAutomationOpenAIApiKey'),os.environ['SOC_OPEN_AI_SERVICE_NAME']
    @staticmethod
    def set_secret(secretname, secretvalue):
        keyvaultname = os.environ['KEYVAULT_NAME']
        credential = DefaultAzureCredential()
        secret_client = SecretClient(vault_url=f"https://{keyvaultname}.vault.azure.net/", credential=credential)
        secret_client.set_secret(secretname, secretvalue)
    #Generate a method to accept the secret name and return the secret value from azure keyvault
    @staticmethod
    def read_secret(secretname):
        #TODO: Replace the keyvaultname with the keyvaultname according to each environment
        keyvaultname = os.environ['KEYVAULT_NAME']
        credential = DefaultAzureCredential()
        secret_client = SecretClient(vault_url=f"https://{keyvaultname}.vault.azure.net/", credential=credential)
        secret = secret_client.get_secret(secretname)
        return secret.value
        
   
    

