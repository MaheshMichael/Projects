import os

from autogen import ConversableAgent

llm_config = {
    "config_list": [
        {
            "model": os.environ["AZURE_OPENAI_CHAT_MODEL"],
            "api_type": "azure",
            "api_key": os.environ["AZURE_OPENAI_API_KEY"],
            "base_url": os.environ["AZURE_OPENAI_ENDPOINT"],
            "api_version": "2023-03-15-preview",
        }
    ]
}

human_proxy = ConversableAgent(
    "human_proxy",
    llm_config=False,  # no LLM used for human proxy
    human_input_mode="ALWAYS",  # always ask for human input
)

agent = ConversableAgent(
    "chatbot",
    llm_config=llm_config,
    code_execution_config=False,  # Turn off code execution, by default it is off.
    function_map=None,  # No registered functions, by default it is None.
    human_input_mode="NEVER",  # Never ask for human input.
)

task = "Describe the conspiracy theory about stargate project"

# Generate
reply = agent.generate_reply(messages=[{"content": f"{task}", "role": "user"}])

print(reply)

# Interact
# reply = human_proxy.initiate_chat(
#     agent,  # this is the same agent with the number as before
#     message=f"{task}",
# )
