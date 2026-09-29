"""Agent seam used by the API: stream_reply(session_id, text, lang, usage=None)."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.agent.graph import build_graph

_graph: CompiledStateGraph | None = None


@dataclass
class TokenUsage:
    """Filled by stream_reply as the model reports usage (Bedrock sends it with the last chunk)."""

    input_tokens: int | None = None
    output_tokens: int | None = None

    def add(self, usage: dict) -> None:
        self.input_tokens = (self.input_tokens or 0) + usage.get("input_tokens", 0)
        self.output_tokens = (self.output_tokens or 0) + usage.get("output_tokens", 0)


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


async def stream_reply(
    session_id: str, text: str, lang: str, usage: TokenUsage | None = None
) -> AsyncIterator[str]:
    graph = _get_graph()
    config = {"configurable": {"thread_id": session_id}}
    inputs = {"messages": [HumanMessage(text)], "lang": lang}
    async for chunk, metadata in graph.astream(inputs, config, stream_mode="messages"):
        if metadata.get("langgraph_node") != "respond" or not isinstance(chunk, AIMessageChunk):
            continue
        if usage is not None and chunk.usage_metadata:
            usage.add(chunk.usage_metadata)
        if piece := chunk.text:
            yield piece
