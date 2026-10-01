import time

import pytest
from botocore.exceptions import ClientError
from langchain_core.messages import AIMessage, HumanMessage

from app import agent
from app.agent.graph import build_graph
from app.config import Settings
from app.sessions import (
    ChatMessage,
    DynamoSessionStore,
    InMemorySessionStore,
    build_session_store,
    get_session_store,
)
from tests.test_agent import RecordingFake


class FakeTable:
    """Just enough of a boto3 Table for DynamoSessionStore (one item per session_id)."""

    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression=None):
        if ConditionExpression and Item["session_id"] in self.items:
            error = {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}}
            raise ClientError(error, "PutItem")
        self.items[Item["session_id"]] = dict(Item)

    def get_item(self, Key, ConsistentRead=False):
        item = self.items.get(Key["session_id"])
        return {"Item": dict(item)} if item else {}

    def update_item(
        self, Key, UpdateExpression, ExpressionAttributeValues, ConditionExpression=None
    ):
        if ConditionExpression and Key["session_id"] not in self.items:
            error = {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}}
            raise ClientError(error, "UpdateItem")
        item = self.items.setdefault(Key["session_id"], {"session_id": Key["session_id"]})
        v = ExpressionAttributeValues
        if UpdateExpression.startswith("SET auth_state = :auth, expires_at"):
            item["auth_state"] = v[":auth"]
        if ":m" in v:
            item["messages"] = v[":m"]
            item["auth_state"] = v[":auth"]
            if ":case" in v:
                item["case_state"] = v[":case"]
            item.setdefault("lang", v[":lang"])
            item.setdefault("created_at", v[":now"])
        if "SET lang = :lang" in UpdateExpression:
            item["lang"] = v[":lang"]
        item["expires_at"] = v[":exp"]


def dynamo_store(table=None, max_messages=40) -> DynamoSessionStore:
    return DynamoSessionStore(table or FakeTable(), ttl_hours=24, max_messages=max_messages)


async def test_dynamo_session_lifecycle():
    store = dynamo_store()
    session = await store.create("es")
    assert (await store.get(session.id)).lang == "es"
    await store.set_lang(session.id, "pt")
    await store.save_messages(
        session.id, "pt", [ChatMessage("user", "olá"), ChatMessage("assistant", "oi, ñ ok")]
    )

    loaded = await store.get(session.id)
    assert loaded.lang == "pt"
    assert loaded.messages == [ChatMessage("user", "olá"), ChatMessage("assistant", "oi, ñ ok")]
    assert await store.get("unknown") is None


async def test_dynamo_session_keeps_its_initial_verification_state():
    store = dynamo_store()
    session = await store.create("es", {"session_customer_id": "C1"})
    assert (await store.get(session.id)).auth == {"session_customer_id": "C1"}


async def test_dynamo_session_keeps_the_handoff_state_unless_replaced():
    store = dynamo_store()
    session = await store.create("es")
    await store.save_messages(session.id, "es", [], case={"handoff": {"case_id": "NB-1"}})
    await store.save_messages(session.id, "es", [ChatMessage("user", "hola")])  # case: None
    assert (await store.get(session.id)).case == {"handoff": {"case_id": "NB-1"}}


async def test_expired_session_is_gone_even_before_ttl_deletes_it():
    table = FakeTable()
    store = dynamo_store(table)
    session = await store.create("es")
    table.items[session.id]["expires_at"] = int(time.time()) - 1
    assert await store.get(session.id) is None


@pytest.mark.parametrize(
    "make", [lambda: dynamo_store(max_messages=4), lambda: InMemorySessionStore(4)]
)
async def test_history_is_capped(make):
    store = make()
    session = await store.create("es")
    messages = [ChatMessage("user" if i % 2 == 0 else "assistant", str(i)) for i in range(10)]
    await store.save_messages(session.id, "es", messages)
    assert [m.content for m in (await store.get(session.id)).messages] == ["6", "7", "8", "9"]


def test_build_session_store_from_settings():
    assert isinstance(build_session_store(Settings(_env_file=None)), InMemorySessionStore)


async def test_conversation_continues_on_another_instance(monkeypatch):
    """Two Lambda instances (own graph, own store object) sharing one table: the second one
    sees the first turn. This is what the in-memory store couldn't do."""
    table = FakeTable()
    model = RecordingFake(messages=iter([AIMessage("uno"), AIMessage("dos")]), calls=[])

    instance_a = dynamo_store(table)
    monkeypatch.setattr("app.agent.get_session_store", lambda: instance_a)
    session = await instance_a.create("es")
    agent._graph = build_graph(model)
    assert "".join([p async for p in agent.stream_reply(session.id, "primera", "es")]) == "uno"

    instance_b = dynamo_store(table)  # cold start: nothing in memory
    monkeypatch.setattr("app.agent.get_session_store", lambda: instance_b)
    agent._graph = build_graph(model)
    assert "".join([p async for p in agent.stream_reply(session.id, "segunda", "es")]) == "dos"

    second_call = model.calls[1]
    assert [type(m) for m in second_call[1:]] == [HumanMessage, AIMessage, HumanMessage]
    assert [m.content for m in second_call[1:]] == [
        "primera",
        "uno",
        "segunda\n\n(Responde en español.)",
    ]
    # The reminder is for the model only: the stored history is the customer's own words.
    stored = (await instance_b.get(session.id)).messages
    assert [m.content for m in stored] == ["primera", "uno", "segunda", "dos"]


async def test_failed_reply_is_not_saved(monkeypatch):
    class Broken(RecordingFake):
        async def _astream(self, *args, **kwargs):
            raise RuntimeError("model down")
            yield  # pragma: no cover

    store = get_session_store()
    session = await store.create("es")
    agent._graph = build_graph(Broken(messages=iter([]), calls=[]))
    with pytest.raises(RuntimeError):
        _ = [p async for p in agent.stream_reply(session.id, "hola", "es")]
    assert (await store.get(session.id)).messages == []


# --- renewing the verification of a session (idle timeout) ----------------------------------------


async def test_set_auth_replaces_only_the_verification_state_of_an_existing_session():
    for store in (InMemorySessionStore(), dynamo_store(FakeTable())):
        session = await store.create("es", {"step": "verified", "verified_until": 1})
        await store.set_auth(session.id, {"step": "verified", "verified_until": 99})
        assert (await store.get(session.id)).auth["verified_until"] == 99
        await store.set_auth("missing", {"step": "verified"})  # nothing is created
        assert await store.get("missing") is None
