import os
import logging
from dataclasses import dataclass, field
from pydantic_graph import BaseNode, GraphRunContext, End
from pydantic_ai import Agent, format_as_xml
from pydantic_ai.messages import ModelMessage
from fastapi import WebSocket
from groq import BaseModel
from dotenv import load_dotenv

from agents.ask_agent import ask_agent
from agents.evaluate_agent import evaluate_agent, EvaluationOutput

# Load environment variables from .env file
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class GraphDeps:
    websocket: WebSocket
    # Dependencies required for the graph, specifically a WebSocket for communication.

@dataclass
class QuestionState:
    question: str | None = None
    ask_agent_messages: list[ModelMessage] = field(default_factory=list)
    evaluate_agent_messages: list[ModelMessage] = field(default_factory=list)
    # State of the question, including the current question, messages for the ask agent, and messages for the evaluate agent.

@dataclass
class Answer(BaseNode[QuestionState, GraphDeps]):
    question: str
    # Node representing the answer to a question.

    async def run(self, ctx: GraphRunContext[QuestionState, GraphDeps]) -> 'Evaluate':
        websocket = ctx.deps['websocket']
        answer = await websocket.receive_text()
        return Evaluate(answer)
        # Receive the answer from the WebSocket and transition to the Evaluate node.

@dataclass
class Ask(BaseNode[QuestionState, GraphDeps]):
    # Node responsible for asking a question.

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
        # Ask a question using the ask agent, update the state, and send the question via WebSocket.

class EvaluationOutput(BaseModel, use_attribute_docstrings=True):
    correct: bool
    """Whether the answer is correct."""
    comment: str
    """Comment on the answer, reprimand the user if the answer is wrong."""
    # Output model for evaluation results, indicating correctness and providing a comment.

@dataclass
class Evaluate(BaseNode[QuestionState, GraphDeps, str]):
    answer: str
    # Node responsible for evaluating the answer.

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
        # Evaluate the answer using the evaluate agent, update the state, and send feedback via WebSocket.

@dataclass
class Reprimand(BaseNode[QuestionState]):
    comment: str
    # Node representing a reprimand for an incorrect answer.

    async def run(self, ctx: GraphRunContext[QuestionState, GraphDeps]) -> Ask:
        ctx.state.question = None
        return Ask()
        # Reset the question state and transition back to the Ask node.