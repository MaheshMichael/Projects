from datetime import datetime,timezone
from uuid import uuid4
from azure.core.exceptions import ResourceExistsError, HttpResponseError
from azure.data.tables import TableClient
from secrets_manager import SecretsManager
import pyodbc
def LogError(message, exception,correlationId,reportId,FileName):
        connectionString = SecretsManager.DBStorageConnectionString
        driver= '{ODBC Driver 17 for SQL Server}'
        db_connection_string = f"""DRIVER={driver};SERVER={SecretsManager.DBSERVER};DATABASE={SecretsManager.DBName};UID={SecretsManager.DBUSER};PWD={SecretsManager.DBPASSWORD}"""
        # dbconnectionString = SecretsManager.read_secret("GLAutomationDatabaseConnectionString")
        try:
          currTime = (datetime.now(timezone.utc) - datetime(1, 1, 1, tzinfo=timezone.utc)).total_seconds() * 10000000
        except Exception as e:
          print("Error in getting current time: {0}".format(str(e)))
        try:
          errorMessage = "An unexpected server error has occurred. Please reach out to support team with Correlation Id: " + correlationId
          conn = pyodbc.connect(db_connection_string)
          query = f"""UPDATE [dbo].[Document] SET DocumentStatusId = 4, ErrorMessage='{errorMessage}' WHERE DocumentId = {reportId}"""
          cursor = conn.cursor()          
          cursor.execute(query)
          conn.commit()
          cursor.close()
          conn.close()
          tableClient = TableClient.from_connection_string(conn_str=connectionString, table_name='LogEvents')
          rowKey = "Error|{0}|{1}".format(message,str(uuid4()))
          partitionKey="0{0}".format(str(int(currTime)))
          entity = {
                          u"PartitionKey": partitionKey,
                          u"RowKey": rowKey,
                          u"Exception":str(exception),
                          u"CorrelationId":correlationId,
                          u"AggregatedProperties":"",
                          u"Level":"Error",
                          u"MessageTemplate":message,
                          u"RenderedMessage":message,
                          u"IPAddress":"NA",
                          u"EventTypeId":"2",
                          u"OperationOrResource":"GenAI Operation",
                          u"UserObjectId":"NA",
                          u"NetworkProtocol":"HTTPS",
                          u"IsSuccess":0
                        }
          resp = tableClient.create_entity(entity=entity)    
        except Exception as e:
            print("Error in logging to table storage: {0}".format(str(e)))
