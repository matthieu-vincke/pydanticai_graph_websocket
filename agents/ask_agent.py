from pydantic_ai import Agent

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

ask_agent = Agent('groq:llama-3.3-70b-versatile', output_type=str)
