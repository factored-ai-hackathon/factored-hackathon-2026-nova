"""LangGraph graph for the chat agent.

MVP: START -> respond -> END. Security steps will be enforced here, in code, as new nodes.
"""

from functools import cache
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph

PROMPTS_DIR = Path(__file__).parent / "prompts"


@cache
def system_prompt(lang: str) -> str:
    return (PROMPTS_DIR / f"{lang}.md").read_text(encoding="utf-8")


class ChatState(MessagesState):
    lang: str


def build_graph(
    model: BaseChatModel, checkpointer: BaseCheckpointSaver | None = None
) -> CompiledStateGraph:
    async def respond(state: ChatState, config: RunnableConfig) -> dict:
        # The system prompt is added per turn (not stored), so a language switch applies at once.
        messages = [SystemMessage(system_prompt(state["lang"])), *state["messages"]]
        reply = await model.ainvoke(messages, config)
        return {"messages": [reply]}

    graph = StateGraph(ChatState)
    # TODO(classify_turn): classify the turn (public question / needs account data / escalate).
    # TODO(auth_gate): KBA + OTP before any personal data; route here from classify_turn.
    # TODO(answer_public): RAG over products and policies for public questions.
    # TODO(handoff): hand over to a human with a summary for ambiguous or high-risk cases.
    graph.add_node("respond", respond)
    graph.add_edge(START, "respond")
    graph.add_edge("respond", END)
    # No checkpointer by default: stream_reply loads and saves the conversation through the session
    # store (DynamoDB when deployed), so the graph itself is stateless.
    return graph.compile(checkpointer=checkpointer)
