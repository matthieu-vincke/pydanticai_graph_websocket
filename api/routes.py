import os
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, status
from pydantic_graph import GraphRunResult
from graph.graph import question_graph, QuestionState, Ask
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Get the API key from environment variables
API_KEY = os.getenv('API_KEY')

if not API_KEY:
    raise ValueError("API_KEY environment variable not set")

app = APIRouter()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Get the API key from the query parameters
    query_params = websocket.query_params
    client_api_key = query_params.get('api_key')

    # Check if the API key is valid
    if client_api_key != API_KEY:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")

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