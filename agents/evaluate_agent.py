from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from groq import BaseModel

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class EvaluationOutput(BaseModel, use_attribute_docstrings=True):
    correct: bool
    """Whether the answer is correct."""
    comment: str
    """Comment on the answer, reprimand the user if the answer is wrong."""

evaluate_agent = Agent(
    'groq:llama-3.3-70b-versatile',
    output_type=EvaluationOutput,
    system_prompt='Given a question and answer, evaluate if the answer is correct.',
)