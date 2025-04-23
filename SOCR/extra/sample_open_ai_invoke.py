import os
from openai import AzureOpenAI

# Replace with your own values
model_name = "gpt-4o"
api_key = os.getenv("OPENAI_API_KEY")
endpoint = os.getenv("ENDPOINT")
api_version = os.getenv("OPENAI_API_VERSION")

client = AzureOpenAI(
    api_key=api_key,  
    api_version=api_version,
    azure_endpoint=endpoint
)

# Send a completion call to generate an answer
print('Sending a test completion job')
start_phrase = 'Write a tagline for an ice cream shop.'

messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is the capital of France?"}
]

# Await the response if the method is asynchronous
response = await client.chat.completions.create(model=model_name, messages=messages, max_tokens=10)
content = response.choices[0].message.content

print(content)
