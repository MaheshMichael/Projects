import re
import tiktoken

from prepdocslib.embeddings import OpenAIEmbeddings
def calculate_token_length(model:str,text: str):
    encoding = tiktoken.encoding_for_model(model)
    token_count = len(encoding.encode(text))
    return token_count
def remove_whitespace(text):
    return re.sub(r'\s+', '', text)
def is_number_and_punctuation(s):
    pattern = r'^\d+(\.\d+)?$'
    return bool(re.match(pattern, s))

def getTokenLimit(openaiModelName:str):
    openai_models = {
        "gpt-3.5-turbo": 4096,
        "gpt-3.5": 4096,
        "text-davinci-003": 4096,
        "curie": 4096,
        "gpt-4":8192,
        "gpt-4-turbo":8192,
        "gpt-4-32k":60000,
        "gpt-4-turbo-preview":8192,
        "gpt-4o":10000000
        # Add more models and their token limits here
    }

    return openai_models.get(openaiModelName, "Model not found")