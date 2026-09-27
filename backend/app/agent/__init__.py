"""Agent seam used by the API: stream_reply(session_id, text, lang)."""

from collections.abc import AsyncIterator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.agent.graph import build_graph

_graph: CompiledStateGraph | None = None


def set_chat_model(model: BaseChatModel) -> None:
    """Rebuild the graph around a given model (tests use a fake one). Resets memory."""
    global _graph
    _graph = build_graph(model)


def _get_graph() -> CompiledStateGraph:
    global _graph
    if _graph is None:
        from app.llm import get_chat_model

        _graph = build_graph(get_chat_model())
    return _graph


async def stream_reply(session_id: str, text: str, lang: str) -> AsyncIterator[str]:
    graph = _get_graph()
    config = {"configurable": {"thread_id": session_id}}
    inputs = {"messages": [HumanMessage(text)], "lang": lang}
    async for chunk, metadata in graph.astream(inputs, config, stream_mode="messages"):
        if metadata.get("langgraph_node") != "respond" or not isinstance(chunk, AIMessageChunk):
            continue
        if piece := chunk.text:
            yield piece
