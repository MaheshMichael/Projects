import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Union
from typing_extensions import Annotated

import autogen
from autogen import Agent
from autogen import ConversableAgent
from autogen import AssistantAgent
from autogen.agentchat.contrib.retrieve_user_proxy_agent import RetrieveUserProxyAgent
from search import single_vector_search
from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv

load_dotenv()

service_endpoint = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
key = os.environ["AZURE_SEARCH_API_KEY"]
k_nearest_neighbors = 20

config_list = [
    {
        "model": os.environ["AZURE_OPENAI_CHAT_MODEL"],
        "api_type": "azure",
        "api_key": os.environ["AZURE_OPENAI_API_KEY"],
        "base_url": os.environ["AZURE_OPENAI_ENDPOINT"],
        "api_version": "2023-03-15-preview",
    }
]

llm_config = {
    "config_list": config_list,
    "timeout": 60,
    "temperature": 0.8,
    "seed": 1234,
}

prompts_dir = os.path.join("prompts")

# Set up Jinja environment and template loader
env = Environment(loader=FileSystemLoader(prompts_dir))

it_apps_generator_template = env.get_template("it_apps_generator.j2")
it_apps_generator_prompt = it_apps_generator_template.render({})

it_apps_reviewer_template = env.get_template("it_apps_reviewer.j2")
it_apps_reviewer_prompt = it_apps_reviewer_template.render({})

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the output folder path
output_folder = os.path.join(os.path.dirname(script_dir), "output")

# Ensure the output folder exists
os.makedirs(output_folder, exist_ok=True)

PROMPT_QA = """Answer user's questions based on the
context provided by the user.

User's question is: {input_question}

Context is: {input_context}
"""


def vector_search_message_generator(sender, recipient, context):
    problem = context.get("problem", "")

    chunks = single_vector_search(problem)

    result = ""

    for i, item in enumerate(chunks, 1):
        result += f"{i}. {item['chunk']}\n"

    result = PROMPT_QA.format(input_question=problem, input_context=result)

    return result


retriever_agent = ConversableAgent(
    "retriever_agent",
    llm_config=False,  # no LLM used for human proxy
    human_input_mode="NEVER",  # always ask for human input
)

it_apps_generator = ConversableAgent(
    name="it_apps_generator",
    system_message=it_apps_generator_prompt,
    # max_consecutive_auto_reply=10,
    llm_config={
        "timeout": 600,
        "cache_seed": 42,
        "config_list": config_list,
    },
    human_input_mode="NEVER",  # never ask for human input
)

it_apps_reviewer = ConversableAgent(
    name="it_apps_reviewer",
    system_message=it_apps_reviewer_prompt,
    # max_consecutive_auto_reply=10,
    llm_config={
        "timeout": 600,
        "cache_seed": 42,
        "config_list": config_list,
    },
    human_input_mode="NEVER",  # never ask for human input
)


def _reset_agents():
    retriever_agent.reset()
    it_apps_generator.reset()
    it_apps_reviewer.reset()


if __name__ == "__main__":
    _reset_agents()

    PROBLEM = "applications in scope or systems in scope or platforms in scope"

    groupchat = autogen.GroupChat(
        agents=[retriever_agent, it_apps_generator, it_apps_reviewer],
        messages=[],
        max_round=3,
        # speaker_selection_method="round_robin",
    )

    manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=llm_config)

    # initial chat
    retriever_agent.initiate_chat(
        manager,
        message=vector_search_message_generator,
        problem=PROBLEM,
    )

    analysis_index = 0
    review_index = 0

    for msg_lst in retriever_agent.chat_messages.values():
        for msg in msg_lst:
            content, name = msg["content"], msg["name"]
            if name == "it_apps_generator":
                # Saving analysis
                file_name = f"analysis_{analysis_index}.txt"
                file_path = os.path.join(output_folder, file_name)

                with open(file_path, "w") as output:
                    output.write(content)

                analysis_index += 1
            elif name == "it_apps_reviewer":
                # Saving review
                file_name = f"review_{review_index}.txt"
                file_path = os.path.join(output_folder, file_name)

                with open(file_path, "w") as output:
                    output.write(content)

                review_index += 1
