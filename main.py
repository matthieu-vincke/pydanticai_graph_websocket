from __future__ import annotations as _annotations

from dataclasses import dataclass, field
from pathlib import Path

import asyncio
import logfire
from groq import BaseModel
from pydantic_graph import (
    BaseNode,
    End,
    Graph,
    GraphRunContext,
    GraphRunResult,
)
from pydantic_graph.persistence.file import FileStatePersistence

from pydantic_ai import Agent, format_as_xml
from pydantic_ai.messages import ModelMessage

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from fastapi.middleware.cors import CORSMiddleware

# 'if-token-present' means nothing will be sent (and the example will work) if you don't have logfire configured
logfire.configure(send_to_logfire='if-token-present')
logfire.instrument_pydantic_ai()

from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv()

ask_agent = Agent('groq:llama-3.3-70b-versatile', output_type=str) # 'openai:gpt-4o'

app = FastAPI()

# Add CORS middleware to allow frontend connections
# More robust CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@dataclass
class GraphDeps:
    websocket: WebSocket

@dataclass
class QuestionState:
    question: str | None = None
    ask_agent_messages: list[ModelMessage] = field(default_factory=list)
    evaluate_agent_messages: list[ModelMessage] = field(default_factory=list)

@dataclass
class Ask(BaseNode[QuestionState, GraphDeps]):
    async def run(self, ctx: GraphRunContext[QuestionState, GraphDeps]) -> Answer:
        print(ctx.deps)
        websocket = ctx.deps['websocket']
        result = await ask_agent.run(
            'Ask a simple question with a single correct answer.',
            message_history=ctx.state.ask_agent_messages,
        )
        ctx.state.ask_agent_messages += result.all_messages()
        ctx.state.question = result.output
        await websocket.send_text(f'Question: {result.output}')
        return Answer(result.output)

@dataclass
class Answer(BaseNode[QuestionState, GraphDeps]):
    question: str

    async def run(self, ctx: GraphRunContext[QuestionState, GraphDeps]) -> Evaluate:
        
        websocket = ctx.deps['websocket']
        answer = await websocket.receive_text()
        return Evaluate(answer)

class EvaluationOutput(BaseModel, use_attribute_docstrings=True):
    correct: bool
    """Whether the answer is correct."""
    comment: str
    """Comment on the answer, reprimand the user if the answer is wrong."""

evaluate_agent = Agent(
    'groq:llama-3.3-70b-versatile',#'openai:gpt-4o',
    output_type=EvaluationOutput,
    system_prompt='Given a question and answer, evaluate if the answer is correct.',
)

@dataclass
class Evaluate(BaseNode[QuestionState, GraphDeps, str]):
    answer: str

    async def run(
        self,
        ctx: GraphRunContext[QuestionState, GraphDeps]
    ) -> End[str] | Reprimand:
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
        #websocket = ctx.deps['websocket']
        #await websocket.send_text(f'Comment: {self.comment}')
        ctx.state.question = None
        return Ask()

question_graph = Graph(
    nodes=(Ask, Answer, Evaluate, Reprimand), state_type=QuestionState
)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    state = QuestionState()
    node = Ask()
    try:
        while True:                        
            if isinstance(node, GraphRunResult):
                await websocket.send_text(f'END: Congrats! You got it right! {node.output}')
                break
            end = await question_graph.run(node, state=state, deps={'websocket': websocket})
            print(f"End type: {type(end)}")
            print(f"End attributes: {dir(end)}")
            node = end
    except WebSocketDisconnect:
        print("Client disconnected")

@app.get("/")
async def get():
    return HTMLResponse(html)

html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>Pydantic Graph Websocket Chat</h1>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>
        <ul id='messages'>
        </ul>
        <script>
            // Dynamically determine WebSocket URL
            function getWebSocketUrl() {
                const host = window.location.host;
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                return `${protocol}//${host}/ws`;
            }
            const socketUrl = getWebSocketUrl();
            console.log(`Attempting to connect to: ${socketUrl}`);
            
            const ws = new WebSocket(socketUrl);
            ws.onmessage = function(event) {
                var messages = document.getElementById('messages')
                var message = document.createElement('li')
                var content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
            };
            function sendMessage(event) {
                var input = document.getElementById("messageText")
                ws.send(input.value)
                input.value = ''
                event.preventDefault()
            }
        </script>
    </body>
</html>
"""

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        # Use forwarded headers for proper URL detection
        proxy_headers=True,
        forwarded_allow_ips="*"
    )