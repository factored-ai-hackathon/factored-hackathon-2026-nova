import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app import agent
from app.api.chat import get_reply_streamer
from app.interactions import MemoryInteractionStore, get_interaction_store
from app.main import app
from app.sessions import get_session_store


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """Return (event, data) pairs from a text/event-stream body."""
    events = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        event, data = None, []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data.append(line[len("data:") :].strip())
        if event:
            events.append((event, json.loads("\n".join(data))))
    return events


def fake_model(*replies: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(r) for r in replies]))


async def echo_reply(session_id: str, text: str, lang: str, usage=None):
    if usage is not None:
        usage.add({"input_tokens": 10, "output_tokens": 3})
    for word in text.split(" "):
        yield word + " "


@pytest.fixture(autouse=True)
def fresh_sessions():
    """Each test starts with an empty in-memory session store (the agent's memory)."""
    get_session_store.cache_clear()
    yield
    get_session_store.cache_clear()


@pytest.fixture(autouse=True)
def interactions():
    """Every test records interactions in memory, never in backend/.interactions."""
    store = MemoryInteractionStore()
    app.dependency_overrides[get_interaction_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_interaction_store, None)


@pytest.fixture
def client():
    app.dependency_overrides[get_reply_streamer] = lambda: echo_reply
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_reply_streamer, None)


@pytest.fixture
def agent_client():
    """Client wired to the real agent graph, with a fake model."""

    def _make(*replies: str) -> TestClient:
        agent.set_chat_model(fake_model(*replies))
        return TestClient(app)

    return _make


@pytest.fixture(autouse=True)
def offline_knowledge(monkeypatch):
    """Knowledge search never calls Bedrock in tests: lexical only, over the real documents."""
    from app.agent import knowledge

    chunks, _ = knowledge.load_chunks()
    kb = knowledge.KnowledgeBase(chunks, knowledge.load_thresholds())
    monkeypatch.setattr(knowledge, "get_knowledge_base", lambda: kb)
    return kb
