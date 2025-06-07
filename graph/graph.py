from pydantic_graph import Graph
from graph.nodes import Ask, Answer, Evaluate, Reprimand, QuestionState
from dotenv import load_dotenv
load_dotenv()

question_graph = Graph(
    nodes=(Ask, Answer, Evaluate, Reprimand), state_type=QuestionState
)