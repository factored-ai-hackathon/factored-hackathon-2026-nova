"""Agent seam used by the API: stream_reply(session_id, text, lang, usage=None).

Yields reply text chunks (str) and out-of-band notices for the customer (Notice).
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.agent import identity
from app.agent.graph import build_graph
from app.sessions import ChatMessage, get_session_store

_graph: CompiledStateGraph | None = None


@dataclass
class Notice:
    """A message for the customer outside the reply, e.g. the demo SMS with the one-time code."""

    kind: str
    text: str


@dataclass
class TokenUsage:
    """Filled by stream_reply: tokens as the model reports them (Bedrock sends them with the last
    chunk), and whether the customer's message was a verification answer (don't log its text)."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    sensitive_input: bool = False
    intent: str | None = None  # the classifier's label for the customer's message
    intent_confidence: float | None = None

    def add(self, usage: dict) -> None:
        self.input_tokens = (self.input_tokens or 0) + usage.get("input_tokens", 0)
        self.output_tokens = (self.output_tokens or 0) + usage.get("output_tokens", 0)


# Nodes that answer with fixed text (not the model), streamed from their state updates.
FIXED_TEXT_NODES = ("auth_gate", "handoff", "human_queue")


def set_chat_model(model: BaseChatModel) -> None:
    """Rebuild the graph around a given model (tests use a fake one)."""
    global _graph
    _graph = build_graph(model)


def _get_graph() -> CompiledStateGraph:
    global _graph
    if _graph is None:
        from app.llm import get_chat_model

        _graph = build_graph(get_chat_model())
    return _graph


def _to_langchain(messages: list[ChatMessage]) -> list[BaseMessage]:
    return [HumanMessage(m.content) if m.role == "user" else AIMessage(m.content) for m in messages]


async def stream_reply(
    session_id: str, text: str, lang: str, usage: TokenUsage | None = None
) -> AsyncIterator[str | Notice]:
    """Stream the reply to `text`. The conversation history and the verification state live in
    the session store, so any instance can continue any conversation; the turn is saved once the
    reply is complete."""
    graph = _get_graph()
    store = get_session_store()
    session = await store.get(session_id)
    history = session.messages if session else []
    auth = session.auth if session else {}
    case = session.case if session else {}
    inputs = {
        "messages": [*_to_langchain(history), HumanMessage(text)],
        "lang": lang,
        "auth": auth,
        "session_id": session_id,
        "case": case,
    }

    reply: list[str] = []
    sensitive = False
    step = None  # graph step of the model call being streamed
    async for mode, payload in graph.astream(inputs, stream_mode=["messages", "updates"]):
        if mode == "messages":
            chunk, metadata = payload
            if metadata.get("langgraph_node") != "respond" or not isinstance(chunk, AIMessageChunk):
                continue
            if usage is not None and chunk.usage_metadata:
                usage.add(chunk.usage_metadata)
            if piece := chunk.text:
                # A second model call in the same turn (after account tools): new paragraph.
                if reply and metadata.get("langgraph_step") != step:
                    piece = "\n\n" + piece
                step = metadata.get("langgraph_step")
                reply.append(piece)
                yield piece
        else:
            for node, delta in payload.items():
                if not delta:
                    continue
                case = delta.get("case", case)
                if usage is not None and (seen := delta.get("turn_intent")):
                    usage.intent, usage.intent_confidence = seen["label"], seen["confidence"]
                if node not in FIXED_TEXT_NODES:
                    continue
                for message in delta.get("messages", []):
                    piece = ("\n\n" if reply else "") + message.text
                    reply.append(piece)
                    yield piece
                for notice in delta.get("notices", []):
                    yield Notice("otp_demo", notice)
                if case_id := delta.get("handoff_notice"):
                    yield Notice("handoff", case_id)
                auth = delta.get("auth", auth)
                sensitive = sensitive or delta.get("sensitive_input", False)

    if usage is not None:
        usage.sensitive_input = sensitive
    # Verification answers (document, date of birth, code) never go into the history.
    user_text = identity.text(lang, "placeholder") if sensitive else text
    turn = [ChatMessage("user", user_text)]
    if reply:  # with an agent on the case, the bot doesn't answer
        turn.append(ChatMessage("assistant", "".join(reply)))
    await store.save_messages(session_id, lang, [*history, *turn], auth=auth, case=case)
