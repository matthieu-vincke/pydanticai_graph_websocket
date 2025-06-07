import os
import logging
from dataclasses import dataclass, field
from pydantic_graph import BaseNode, GraphRunContext, End
from pydantic_ai import Agent, format_as_xml
from pydantic_ai.messages import ModelMessage
from fastapi import WebSocket
from groq import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class GraphDeps:
    websocket: WebSocket

@dataclass
class QuestionState:
    question: str | None = None
    ask_agent_messages: list[ModelMessage] = field(default_factory=list)
    evaluate_agent_messages: list[ModelMessage] = field(default_factory=list)

ask_agent = Agent('groq:llama-3.3-70b-versatile', output_type=str)

@dataclass
class Answer(BaseNode[QuestionState, GraphDeps]):
    question: str

    async def run(self, ctx: GraphRunContext[QuestionState, GraphDeps]) -> 'Evaluate':
        websocket = ctx.deps['websocket']
        answer = await websocket.receive_text()
        return Evaluate(answer)

@dataclass
class Ask(BaseNode[QuestionState, GraphDeps]):
    async def run(self, ctx: GraphRunContext[QuestionState, GraphDeps]) -> Answer:
        logger.info(ctx.deps)
        websocket = ctx.deps['websocket']
        result = await ask_agent.run(
            'Ask a simple question with a single correct answer.',
            message_history=ctx.state.ask_agent_messages,
        )
        ctx.state.ask_agent_messages += result.all_messages()
        ctx.state.question = result.output
        await websocket.send_text(f'Question: {result.output}')
        return Answer(result.output)

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

@dataclass
class Evaluate(BaseNode[QuestionState, GraphDeps, str]):
    answer: str

    async def run(
        self,
        ctx: GraphRunContext[QuestionState, GraphDeps]
    ) -> End[str] | 'Reprimand':
        websocket = ctx.deps['websocket']
        assert ctx.state.question is not None
        result = await evaluate_agent.run(
            format_as_xml({'question': ctx.state.question, 'answer': self.answer}),
            message_history=ctx.state.evaluate_agent_messages,
        )
        ctx.state.evaluate_agent_messages += result.all_messages()
        if result.output.correct:
            await websocket.send_text(f'Correct Answer! {result.output.comment}')
            return End(result.output.comment)
        else:
            await websocket.send_text(f'This is Bad! {result.output.comment}')
            return Reprimand(result.output.comment)

@dataclass
class Reprimand(BaseNode[QuestionState]):
    comment: str

    async def run(self, ctx: GraphRunContext[QuestionState, GraphDeps]) -> Ask:
        ctx.state.question = None
        return Ask()