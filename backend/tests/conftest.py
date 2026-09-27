import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app import agent
from app.api.chat import get_reply_streamer
from app.main import app


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


async def echo_reply(session_id: str, text: str, lang: str):
    for word in text.split(" "):
        yield word + " "


@pytest.fixture
def client():
    app.dependency_overrides[get_reply_streamer] = lambda: echo_reply
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def agent_client():
    """Client wired to the real agent graph, with a fake model."""

    def _make(*replies: str) -> TestClient:
        agent.set_chat_model(fake_model(*replies))
        return TestClient(app)

    return _make
