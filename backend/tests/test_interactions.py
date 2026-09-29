import json

import pytest
from botocore.exceptions import ClientError

from app.api.chat import get_reply_streamer
from app.config import Settings
from app.interactions import (
    DynamoInteractionStore,
    JsonlInteractionStore,
    NoopInteractionStore,
    Turn,
    build_interaction_store,
    mask_pii,
)
from app.main import app
from tests.conftest import parse_sse


def make_turn(**overrides) -> Turn:
    fields = dict(
        session_id="s1",
        message_id="m1",
        lang="es",
        user_text="Mi tarjeta 4111 1111 1111 1234 no pasa, escribe a ana@correo.com",
        reply_text="Revisaré la tarjeta ****1234",
        status="ok",
        model="test-model",
        input_tokens=10,
        output_tokens=5,
        first_token_ms=120,
        total_ms=900,
    )
    return Turn(**{**fields, **overrides})


# --- masking -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("tarjeta 4111 1111 1111 1234", "tarjeta ****1234"),
        ("cuenta 0012-3456-7890", "cuenta ****7890"),
        ("cuenta 123456789012", "cuenta ****9012"),
        ("escribe a ana.perez+banco@correo.com.co", "escribe a [email]"),
        ("pagué 250000 COP el 12/09/2026", "pagué 250000 COP el 12/09/2026"),
        ("mi PIN es 1234", "mi PIN es 1234"),
    ],
)
def test_mask_pii(text, expected):
    assert mask_pii(text) == expected


def test_metrics_have_no_text():
    metrics = make_turn().metrics()
    assert "user_text" not in metrics and "reply_text" not in metrics
    assert metrics["total_ms"] == 900


# --- JSONL store ---------------------------------------------------------------


async def test_jsonl_store_saves_masked_turn_and_feedback(tmp_path):
    path = tmp_path / "sub" / "interactions.jsonl"
    store = JsonlInteractionStore(path)
    await store.save_turn(make_turn())
    assert await store.set_feedback("s1", "m1", "down", "no entendió 4111111111111234")
    assert not await store.set_feedback("s1", "unknown", "up", None)

    turn, feedback = [json.loads(line) for line in path.read_text().splitlines()]
    assert turn["type"] == "turn"
    assert "4111" not in turn["user_text"] and "[email]" in turn["user_text"]
    assert feedback == {
        **feedback,
        "type": "feedback",
        "message_id": "m1",
        "feedback": "down",
        "feedback_comment": "no entendió ****1234",
    }


async def test_jsonl_feedback_without_file(tmp_path):
    assert not await JsonlInteractionStore(tmp_path / "none.jsonl").set_feedback(
        "s", "m", "up", None
    )


# --- DynamoDB store (fake table) -----------------------------------------------


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        self.items[(Item["session_id"], Item["message_id"])] = Item

    def update_item(self, Key, ExpressionAttributeValues, **kwargs):
        item = self.items.get((Key["session_id"], Key["message_id"]))
        if item is None:
            error = {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}}
            raise ClientError(error, "UpdateItem")
        item["feedback"] = ExpressionAttributeValues[":r"]


async def test_dynamo_store_puts_item_with_ttl_and_updates_feedback():
    table = FakeTable()
    store = DynamoInteractionStore(table, ttl_days=30)
    await store.save_turn(make_turn(error_code=None))

    item = table.items[("s1", "m1")]
    assert "error_code" not in item  # None values are not stored
    assert "4111" not in item["user_text"]
    assert item["expires_at"] > 0

    assert await store.set_feedback("s1", "m1", "up", None)
    assert table.items[("s1", "m1")]["feedback"] == "up"
    assert not await store.set_feedback("s1", "missing", "up", None)


def test_build_store_from_settings(tmp_path):
    assert isinstance(
        build_interaction_store(Settings(interactions_store="none")), NoopInteractionStore
    )
    store = build_interaction_store(Settings(interactions_path=tmp_path / "i.jsonl"))
    assert isinstance(store, JsonlInteractionStore)


# --- API -------------------------------------------------------------------------


def send(client, text="hola banco"):
    sid = client.post("/v1/chat/sessions").json()["session_id"]
    r = client.post(f"/v1/chat/sessions/{sid}/messages", json={"text": text, "lang": "es"})
    return sid, parse_sse(r.text)


def test_turn_is_recorded_with_metrics(client, interactions):
    sid, events = send(client, "mi cuenta 123456789012")
    message_id = events[-1][1]["message_id"]

    turn = interactions.turns[(sid, message_id)]
    assert turn["status"] == "ok"
    assert turn["user_text"] == "mi cuenta ****9012"
    assert turn["reply_text"] == "mi cuenta ****9012 "  # the echo reply is masked too
    assert (turn["input_tokens"], turn["output_tokens"]) == (10, 3)
    assert turn["first_token_ms"] is not None and turn["total_ms"] >= turn["first_token_ms"]
    assert turn["model"]


def test_feedback(client, interactions):
    sid, events = send(client)
    message_id = events[-1][1]["message_id"]
    url = f"/v1/chat/sessions/{sid}/messages/{message_id}/feedback"

    assert client.post(url, json={"rating": "down", "comment": "no ayudó"}).status_code == 204
    assert interactions.turns[(sid, message_id)]["feedback"] == "down"
    assert client.post(url, json={"rating": "meh"}).status_code == 422
    assert client.post(url, json={"rating": "up", "comment": "x" * 501}).status_code == 422
    bad = f"/v1/chat/sessions/{sid}/messages/unknown/feedback"
    assert client.post(bad, json={"rating": "up"}).status_code == 404


async def failing_reply(session_id, text, lang, usage=None):
    yield "Hola"
    raise RuntimeError("boom")


def test_failed_turn_is_recorded(client, interactions):
    app.dependency_overrides[get_reply_streamer] = lambda: failing_reply
    sid, events = send(client)
    assert events[-1][0] == "error"
    (turn,) = interactions.turns.values()
    assert (turn["status"], turn["error_code"], turn["reply_text"]) == (
        "error",
        "llm_error",
        "Hola",
    )


def test_store_failure_does_not_break_chat(client, interactions):
    async def broken(turn):
        raise RuntimeError("store down")

    interactions.save_turn = broken
    _, events = send(client)
    assert events[-1][0] == "done"
