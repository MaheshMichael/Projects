import logging
import requests
from azure.identity import DefaultAzureCredential

from secrets_manager import SecretsManager

class ApiManager:
    def __init__(self):
        # self.apiUrl = 'https://uscdadvecnwap0k.azurewebsites.net/api/DocumentsCallback'
        self.apiUrl = SecretsManager.APIURL
        #self.apiUrl = 'https://uscdadvecnwap0k.azurewebsites.net/api/Documents/callback'

    def callback_api(self, data_json):
        #get auth token
        # credential = DefaultAzureCredential()
        # # Call your API
        # token_credential = credential.get_token('https://management.azure.com/.default')
        # access_token=token_credential.token
        url = self.apiUrl
        headers = {
            'Content-type': 'application/json', 
            'Accept': 'application/json',
            'Authorization': f"Bearer {''}",

        }
        response = requests.post(url, 
                                headers=headers,
                                data = data_json )
        return response
