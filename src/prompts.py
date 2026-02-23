from langchain.prompts import PromptTemplate

from src.config import AI_SYSTEM_PROMPT


sql_agent_prompt = PromptTemplate.from_template(AI_SYSTEM_PROMPT)
