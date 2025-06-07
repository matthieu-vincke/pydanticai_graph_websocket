import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic_graph import GraphRunResult
from graph.graph import question_graph, QuestionState, Ask
from dotenv import load_dotenv
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

app = APIRouter()

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
            logger.info(f"End type: {type(end)}")
            logger.info(f"End attributes: {dir(end)}")
            node = end
    except WebSocketDisconnect:
        logger.info("Client disconnected")