import os
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2024-08-01-preview",
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
)

response = client.chat.completions.create(
    model="gpt-4o-mini",  # model = "deployment_name".
    messages=[
        {
            "role": "user",
            "content": "Pros and cons of skoda octavia vs skoda superb",
        },
    ],
)

# print(response)
# print(response.model_dump_json(indent=2))
print(response.choices[0].message.content)
