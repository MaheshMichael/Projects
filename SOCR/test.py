import os  # Importing the os module to interact with the operating system
from typing import Annotated  # Importing Annotated for type hinting
from typing_extensions import TypedDict  # Importing TypedDict for creating typed dictionaries
from langgraph.graph import StateGraph, START, END  # Importing StateGraph and constants for graph management
from langgraph.graph.message import add_messages  # Importing function to manage message states
from langchain_openai import AzureChatOpenAI  # Importing AzureChatOpenAI for interacting with OpenAI's API

from dotenv import load_dotenv  # Importing dotenv to load environment variables from a .env file

load_dotenv()  # Load environment variables from .env file

# Load environment variables for OpenAI API
model_name = "gpt-4o"  # Specify the model name
api_key = os.getenv("OPENAI_API_KEY")  # Get OpenAI API key from environment variables
endpoint = os.getenv("ENDPOINT")  # Get endpoint from environment variables
api_version = os.getenv("OPENAI_API_VERSION")  # Get API version from environment variables
langsmith = os.getenv('LANGSMITH_API_KEY')  # Get Langsmith API key from environment variables

# Set environment variables for Langchain
os.environ["LANGCHAIN_API_KEY"] = langsmith
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGCHAIN_PROJECT"] = "SOCR-Test"

class State(TypedDict):
  # Define the State class with a TypedDict to hold the chatbot's state
  messages: Annotated[list, add_messages]  # Messages have the type "list". The `add_messages` function defines how this state key should be updated

# Create a StateGraph instance to manage the chatbot's state
graph_builder = StateGraph(State)

# Initialize the AzureChatOpenAI instance with the specified parameters
llm = AzureChatOpenAI(
    azure_deployment=model_name,  # Specify the Azure deployment
    api_version=api_version,  # Specify the API version
    azure_endpoint=endpoint,  # Specify the Azure endpoint
    temperature=0,  # Set the temperature for response variability
    max_tokens=None,  # Set maximum tokens for the response
    timeout=None,  # Set timeout for the request
    max_retries=2,  # Set maximum retries for the request
)

def chatbot(state: State):
  # Define the chatbot function that takes the current state and returns the response
  return {"messages": llm.invoke(state['messages'])}  # Invoke the language model with the current messages

# Add the chatbot function as a node in the graph
graph_builder.add_node("chatbot", chatbot)

# Define the edges of the graph
graph_builder.add_edge(START, "chatbot")  # Connect the start node to the chatbot node
graph_builder.add_edge("chatbot", END)  # Connect the chatbot node to the end node

# Compile the graph
graph = graph_builder.compile()

# Main loop for user interaction
while True:
  user_input = input("User: ")  # Get user input

  if user_input.lower() in ["quit", "q"]:  # Check for exit commands
    print("Good Bye")  # Print goodbye message
    break  # Exit the loop

  for event in graph.stream({'messages': ("user", user_input)}):  # Stream events from the graph
    # print(event.values())  # Print event values

    for value in event.values():  # Iterate through event values
      # print(value['messages'])  # Print the messages from the event
      print("Assistant:", value["messages"].content)  # Print the assistant's response
