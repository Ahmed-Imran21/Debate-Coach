from coaching_engine.llm.client import LLMClient
from coaching_engine.llm.prompts import (
    SYSTEM_PROMPT,
    FEEDBACK_RESPONSE_SCHEMA,
)


client = LLMClient()

response = client.generate(
    system_prompt=SYSTEM_PROMPT,
    user_prompt="""
Analyze this simple debate statement:

"School uniforms should be mandatory because they reduce
distractions and create a more equal environment for students."

Return useful argumentation feedback.
""",
    response_schema=FEEDBACK_RESPONSE_SCHEMA,
)

print(response)