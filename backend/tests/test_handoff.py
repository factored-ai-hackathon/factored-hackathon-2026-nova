"""Human handoff: the case the agent receives, the bot staying out while it's open, the agent
console and the customer's polling (decision 27)."""

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app import agent
from app.agent import Notice
from app.agent.graph import build_graph
from app.agent.handoff import DynamoCaseStore, InMemoryCaseStore, get_case_store
from app.agent.identity import SESSION_CUSTOMER
from app.main import app
from app.sessions import get_session_store
from tests.test_account_tools import SpyData, ToolCallingFake, call, verified_auth

KEY = {"key": "Asesor2026"}


def handoff_call(reason="customer_request", summary="Quiere hablar con un asesor", **extra):
    args = {"reason": reason, "summary": summary, "open_questions": ["¿Monto exacto?"], **extra}
    return AIMessage("", tool_calls=[{"name": "request_human_agent", "args": args, "id": "h1"}])


@pytest.fixture
def cases():
    store = InMemoryCaseStore()
    app.dependency_overrides[get_case_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_case_store, None)


async def say(session_id, text, model, cases, data=None):
    agent._graph = build_graph(model, account_data=data or SpyData(), case_store=cases)
    try:
        pieces = [p async for p in agent.stream_reply(session_id, text, "es")]
    finally:
        agent._graph = None
    reply = "".join(p for p in pieces if isinstance(p, str))
    return reply, [p for p in pieces if isinstance(p, Notice)]


async def test_handoff_builds_the_case_from_code_facts_and_evidence(cases):
    session = await get_session_store().create("es", verified_auth())
    model = ToolCallingFake(
        replies=[
            call("get_my_transactions", {"status": "declined"}),
            AIMessage("Encontré un rechazo."),
            # The model tries to put someone else in the case: facts come from the session.
            handoff_call(reason="dispute", customer_id="demo-002", first_name="Ana"),
        ],
        calls=[],
    )
    await say(session.id, "me rechazaron una compra", model, cases)
    reply, notices = await say(session.id, "quiero disputarla con una persona", model, cases)

    [case] = await cases.list_recent()
    assert "asesor humano" in reply and case["case_id"] in reply
    assert notices == [Notice("handoff", case["case_id"])]
    assert case["status"] == "waiting" and case["reason"] == "dispute"
    assert case["summary"] == "Quiere hablar con un asesor"
    assert case["open_questions"] == ["¿Monto exacto?"]
    assert case["verified_facts"] == {
        "identity_verified": True,
        "customer_id": "demo-001",
        "first_name": "Miguel",
        "logged_in_customer_id": "demo-001",
    }
    [evidence] = case["evidence"]
    assert evidence["tool"] == "get_my_transactions" and "TecnoMundo" in evidence["result"]
    assert [m["role"] for m in case["transcript"]][:2] == ["customer", "assistant"]
    stored = await get_session_store().get(session.id)
    assert stored.case["handoff"] == {"case_id": case["case_id"], "status": "waiting"}


async def test_unverified_customers_can_be_handed_over_without_identity_facts(cases):
    session = await get_session_store().create("es", {SESSION_CUSTOMER: "demo-001"})
    model = ToolCallingFake(replies=[handoff_call(reason="fraud_or_security")], calls=[])
    await say(session.id, "me robaron la tarjeta", model, cases)
    [case] = await cases.list_recent()
    assert case["verified_facts"]["identity_verified"] is False
    assert case["verified_facts"]["customer_id"] is None


async def test_while_the_case_is_open_the_model_is_not_called(cases):
    session = await get_session_store().create("es", verified_auth())
    model = ToolCallingFake(replies=[handoff_call()], calls=[])
    await say(session.id, "quiero un asesor", model, cases)
    reply, _ = await say(session.id, "¿sigue ahí?", model, cases)  # no replies left in the fake
    [case] = await cases.list_recent()
    assert "quedó en el caso" in reply
    assert case["messages"] == [
        {"from": "customer", "text": "¿sigue ahí?", "at": case["messages"][0]["at"]}
    ]
    assert len(model.calls) == 1


# --- agent console and the customer's side --------------------------------------------------


async def open_case(cases) -> tuple[str, str]:
    session = await get_session_store().create("es", verified_auth())
    await say(
        session.id, "quiero un asesor", ToolCallingFake(replies=[handoff_call()], calls=[]), cases
    )
    [case] = await cases.list_recent()
    return session.id, case["case_id"]


def test_console_needs_the_key(client, cases):
    assert client.post("/v1/agent/cases", json={"key": "wrong"}).status_code == 401
    assert client.post("/v1/agent/cases", json=KEY).json() == {
        "cases": [],
        "stats": {"waiting": 0, "active": 0, "closed": 0, "faithfulness_avg": None},
    }


async def test_agent_takes_replies_and_closes_and_the_customer_sees_it(client: TestClient, cases):
    session_id, case_id = await open_case(cases)
    [listed] = client.post("/v1/agent/cases", json=KEY).json()["cases"]
    assert listed["case_id"] == case_id and listed["customer"] == "Miguel"
    assert client.post(f"/v1/agent/cases/{case_id}", json=KEY).json()["summary"]

    poll = lambda after=0: client.post(  # noqa: E731
        f"/v1/chat/sessions/{session_id}/handoff", json={"after": after}
    ).json()
    assert poll()["status"] == "waiting" and poll()["messages"] == []

    r = client.post(f"/v1/agent/cases/{case_id}/take", json={**KEY, "agent_name": "Laura"})
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert (
        client.post(f"/v1/agent/cases/{case_id}/take", json={**KEY, "agent_name": "X"}).status_code
        == 409
    )
    client.post(f"/v1/agent/cases/{case_id}/reply", json={**KEY, "text": "Hola Miguel, ya reviso."})

    update = poll()
    assert update["status"] == "active" and update["agent_name"] == "Laura"
    assert [m["from"] for m in update["messages"]] == ["system", "agent"]
    assert update["messages"][1]["text"] == "Hola Miguel, ya reviso."
    assert poll(update["next"])["messages"] == []

    # While an agent is on it, the customer's messages go to the case and the bot doesn't answer.
    reply, _ = await say(session_id, "gracias", ToolCallingFake(replies=[], calls=[]), cases)
    assert reply == ""
    assert (await cases.get(case_id))["messages"][-1]["from"] == "customer"

    session = await get_session_store().get(session_id)
    assert session.messages[-2].content == "[Laura] Hola Miguel, ya reviso."  # context for Nova

    client.post(f"/v1/agent/cases/{case_id}/close", json=KEY)
    closing = poll(update["next"])
    assert closing["status"] == "closed" and "cerró el caso" in closing["messages"][-1]["text"]
    # Back to the bot.
    reply, _ = await say(
        session_id, "hola", ToolCallingFake(replies=[AIMessage("¡Hola!")], calls=[]), cases
    )
    assert reply == "¡Hola!"


async def test_polling_only_returns_the_sessions_own_case(client, cases):
    _, case_id = await open_case(cases)
    other = await get_session_store().create("es", {})
    other.case = {"handoff": {"case_id": case_id, "status": "waiting"}}  # forged state
    await get_session_store().save_messages(other.id, "es", [], auth={}, case=other.case)
    body = client.post(f"/v1/chat/sessions/{other.id}/handoff", json={"after": 0}).json()
    assert body["status"] == "none" and body["messages"] == []


async def test_replying_before_taking_or_to_unknown_cases_is_refused(client, cases):
    _, case_id = await open_case(cases)
    assert (
        client.post(f"/v1/agent/cases/{case_id}/reply", json={**KEY, "text": "x"}).status_code
        == 409
    )
    assert (
        client.post("/v1/agent/cases/NB-NOPE/reply", json={**KEY, "text": "x"}).status_code == 404
    )


# --- DynamoDB ---------------------------------------------------------------------------------


class FakeCasesTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        self.items[Item["case_id"]] = Item

    def get_item(self, Key, ConsistentRead=False):
        item = self.items.get(Key["case_id"])
        return {"Item": item} if item else {}

    def scan(self, **kwargs):
        return {"Items": list(self.items.values())}


async def test_dynamo_case_store_round_trip():
    store = DynamoCaseStore(FakeCasesTable(), ttl_days=7)
    await store.create(
        {"case_id": "NB-1", "status": "waiting", "created_at": "2026-06-01", "messages": []}
    )
    await store.create(
        {"case_id": "NB-2", "status": "waiting", "created_at": "2026-06-02", "messages": []}
    )
    await store.update("NB-1", status="active", agent_name="Laura")
    await store.add_message("NB-1", "agent", "hola")
    one = await store.get("NB-1")
    assert one["status"] == "active" and one["messages"][0]["text"] == "hola"
    assert [c["case_id"] for c in await store.list_recent()] == ["NB-2", "NB-1"]
    assert await store.update("NB-9", status="x") is None
