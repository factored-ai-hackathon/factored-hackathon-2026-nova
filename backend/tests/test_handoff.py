"""Human handoff: the case the agent receives, the bot staying out while it's open, the agent
console and the customer's polling (decision 27)."""

import asyncio
import json
import threading

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app import agent
from app.agent import Notice
from app.agent.graph import build_graph
from app.agent.handoff import (
    AlreadyRated,
    DynamoCaseStore,
    InMemoryCaseStore,
    RatingConflict,
    get_case_store,
)
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


async def extra_case(cases) -> tuple[str, str]:
    """Another waiting case with its own session (open_case expects the store to be empty)."""
    from app.agent.handoff import build_case

    session = await get_session_store().create("es", verified_auth())
    case = build_case(
        session_id=session.id,
        lang="es",
        args={},
        auth={},
        evidence=[],
        transcript=[],
        verified=False,
    )
    await cases.create(case)
    state = {"handoff": {"case_id": case["case_id"], "status": "waiting"}}
    await get_session_store().save_messages(session.id, "es", [], auth=session.auth, case=state)
    return session.id, case["case_id"]


def test_console_needs_the_key(client, cases):
    assert client.post("/v1/agent/cases", json={"key": "wrong"}).status_code == 401
    assert client.post("/v1/agent/cases", json=KEY).json() == {
        "cases": [],
        "stats": {
            "waiting": 0,
            "active": 0,
            "closed": 0,
            "faithfulness_avg": None,
            "satisfaction_avg": None,
            "rated": 0,
        },
    }


async def test_the_console_never_returns_the_customers_session_id(client: TestClient, cases):
    # The session id is the customer's chat credential; the console key is a published demo value.
    session_id, case_id = await open_case(cases)
    responses = [
        client.post("/v1/agent/cases", json=KEY),
        client.post(f"/v1/agent/cases/{case_id}", json=KEY),
        client.post(f"/v1/agent/cases/{case_id}/take", json={**KEY, "agent_name": "Laura"}),
        client.post(f"/v1/agent/cases/{case_id}/reply", json={**KEY, "text": "Hola"}),
        client.post(f"/v1/agent/cases/{case_id}/close", json=KEY),
        client.post(f"/v1/agent/cases/{case_id}/close", json=KEY),  # already closed
    ]
    for r in responses:
        assert r.status_code == 200
        assert session_id not in r.text and "session_id" not in r.json()
    assert (await cases.get(case_id))["session_id"] == session_id  # still stored, just not shown


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
        self.lock = threading.Lock()

    def put_item(self, Item, **kwargs):
        with self.lock:
            old = self.items.get(Item["case_id"])
            if kwargs.get("ConditionExpression"):
                values = kwargs["ExpressionAttributeValues"]
                ok = (
                    old is not None
                    and "rating" not in old
                    and old["status"] == values[":closed"]
                    and old["case_json"] == values[":seen"]
                )
                if not ok:
                    raise ClientError(
                        {"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem"
                    )
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


# --- satisfaction rating (decision 46) -----------------------------------------------------------


def rate(client, session_id, rating):
    return client.post(f"/v1/chat/sessions/{session_id}/handoff/rating", json={"rating": rating})


async def test_the_customer_rates_the_advisor_once_after_the_case_closes(client, cases):
    session_id, case_id = await open_case(cases)
    # Not closed yet (waiting, then active): nothing to rate.
    assert rate(client, session_id, 5).status_code == 404
    client.post(f"/v1/agent/cases/{case_id}/take", json={**KEY, "agent_name": "Laura"})
    assert rate(client, session_id, 5).status_code == 404
    client.post(f"/v1/agent/cases/{case_id}/close", json=KEY)

    for bad in (True, 3.5, "4", None, 0, 6, -1):
        assert rate(client, session_id, bad).status_code == 422
    missing = client.post(f"/v1/chat/sessions/{session_id}/handoff/rating", json={})
    assert missing.status_code == 422
    assert (await cases.get(case_id)).get("rating") is None
    poll = client.post(f"/v1/chat/sessions/{session_id}/handoff", json={"after": 0}).json()
    assert poll["status"] == "closed" and poll["rating"] is None

    res = rate(client, session_id, 4)
    assert res.status_code == 200 and res.json() == {"case_id": case_id, "rating": 4}
    saved = await cases.get(case_id)
    assert saved["rating"] == 4 and saved["rated_at"]
    assert rate(client, session_id, 1).status_code == 409  # one rating per case
    assert (await cases.get(case_id))["rating"] == 4
    poll = client.post(f"/v1/chat/sessions/{session_id}/handoff", json={"after": 0}).json()
    assert poll["rating"] == 4


async def test_a_session_cannot_rate_someone_elses_case_or_an_unknown_session(client, cases):
    session_id, case_id = await open_case(cases)
    client.post(f"/v1/agent/cases/{case_id}/close", json=KEY)
    other = await get_session_store().create("es", {})
    forged = {"handoff": {"case_id": case_id, "status": "closed"}}  # forged state
    await get_session_store().save_messages(other.id, "es", [], auth={}, case=forged)
    assert rate(client, other.id, 5).status_code == 404
    assert rate(client, "no-such-session", 5).status_code == 404
    assert (await cases.get(case_id)).get("rating") is None


async def test_the_console_shows_the_rating_and_the_queue_average(client, cases):
    session_id, case_id = await open_case(cases)
    client.post(f"/v1/agent/cases/{case_id}/close", json=KEY)
    assert client.post(f"/v1/agent/cases/{case_id}", json=KEY).json()["rating"] is None
    rate(client, session_id, 4)
    other_session, other_case = await extra_case(cases)
    client.post(f"/v1/agent/cases/{other_case}/close", json=KEY)
    rate(client, other_session, 5)
    _, third_case = await extra_case(cases)  # never rated: not in the average
    queue = client.post("/v1/agent/cases", json=KEY).json()
    assert queue["stats"]["rated"] == 2 and queue["stats"]["satisfaction_avg"] == 4.5
    ratings = {c["case_id"]: c["rating"] for c in queue["cases"]}
    assert ratings == {case_id: 4, other_case: 5, third_case: None}
    detail = client.post(f"/v1/agent/cases/{case_id}", json=KEY).json()
    assert detail["rating"] == 4 and "session_id" not in detail


def test_satisfaction_aggregate_math():
    from app.agent.handoff import satisfaction

    empty = satisfaction([])
    assert empty["rated"] == 0 and empty["mean"] is None
    assert empty["distribution"] == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    assert empty["window"] == {"first": None, "last": None}
    got = satisfaction(
        [
            {"rating": 5, "rated_at": "2026-10-02T10:00:00+00:00"},
            {"rating": 5, "rated_at": "2026-10-01T10:00:00+00:00"},
            {"rating": 2, "rated_at": None},
        ]
    )
    assert got["rated"] == 3 and got["mean"] == 4.0
    assert got["distribution"] == {"1": 0, "2": 1, "3": 0, "4": 0, "5": 2}
    assert got["window"] == {
        "first": "2026-10-01T10:00:00+00:00",
        "last": "2026-10-02T10:00:00+00:00",
    }


async def test_memory_store_ratings_are_numbers_only():
    store = InMemoryCaseStore()
    await store.create({"case_id": "NB-1", "status": "closed", "created_at": "x", "messages": []})
    await store.create({"case_id": "NB-2", "status": "closed", "created_at": "y", "messages": []})
    await store.update("NB-2", rating=3, rated_at="2026-10-02T10:00:00+00:00")
    assert await store.ratings() == [{"rating": 3, "rated_at": "2026-10-02T10:00:00+00:00"}]


async def test_dynamo_store_keeps_the_rating_on_the_item_and_scans_only_that():
    table = FakeCasesTable()
    seen = []
    scan = table.scan
    table.scan = lambda **kw: (seen.append(kw), scan(**kw))[1]
    store = DynamoCaseStore(table, ttl_days=7)
    for n in (1, 2):
        await store.create(
            {"case_id": f"NB-{n}", "status": "closed", "created_at": "x", "messages": []}
        )
    await store.update("NB-1", rating=5, rated_at="2026-10-02T10:00:00+00:00")
    assert table.items["NB-1"]["rating"] == 5 and "rating" not in table.items["NB-2"]
    assert await store.ratings() == [{"rating": 5, "rated_at": "2026-10-02T10:00:00+00:00"}]
    assert seen[-1]["ProjectionExpression"] == "#r, rated_at"  # never the case text


async def closed_pair(store, n=1):
    for i in range(1, n + 1):
        await store.create(
            {"case_id": f"NB-{i}", "status": "closed", "created_at": "x", "messages": []}
        )


async def test_memory_rate_is_one_per_case_and_atomic_under_gather():
    # Documents the guarantee, not a regression guard: the memory store checks and sets with no
    # await in between, so this passes even without the fix. The Dynamo fake tests are the guard.
    store = InMemoryCaseStore()
    await store.create({"case_id": "NB-1", "status": "active", "created_at": "x", "messages": []})
    assert await store.rate("NB-1", 5, "t") is None  # not closed
    assert await store.rate("NB-9", 5, "t") is None  # unknown
    await store.update("NB-1", status="closed")
    results = await asyncio.gather(
        store.rate("NB-1", 4, "t1"), store.rate("NB-1", 2, "t2"), return_exceptions=True
    )
    assert sum(isinstance(r, AlreadyRated) for r in results) == 1
    assert sum(isinstance(r, dict) for r in results) == 1
    winner = next(r for r in results if isinstance(r, dict))
    assert (await store.get("NB-1"))["rating"] == winner["rating"]
    with pytest.raises(AlreadyRated):
        await store.rate("NB-1", 1, "t3")


async def test_dynamo_rate_is_conditional_and_atomic_under_concurrency():
    table = FakeCasesTable()
    store = DynamoCaseStore(table, ttl_days=7)
    await closed_pair(store)
    results = await asyncio.gather(
        *(store.rate("NB-1", n, f"t{n}") for n in (1, 2, 3, 4)), return_exceptions=True
    )
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, AlreadyRated) for r in results) == 3
    winner = next(r for r in results if isinstance(r, dict))["rating"]
    assert table.items["NB-1"]["rating"] == winner
    with pytest.raises(AlreadyRated):
        await store.rate("NB-1", 5, "later")
    assert await store.rate("NB-9", 5, "t") is None


async def test_dynamo_rate_requires_closed_and_keeps_a_concurrent_message():
    table = FakeCasesTable()
    store = DynamoCaseStore(table, ttl_days=7)
    await store.create({"case_id": "NB-1", "status": "active", "created_at": "x", "messages": []})
    assert await store.rate("NB-1", 5, "t") is None and "rating" not in table.items["NB-1"]
    await store.update("NB-1", status="closed")
    put = table.put_item
    raced = []

    def put_after_a_message(Item, **kwargs):  # the advisor's message lands before our put
        if not raced:
            raced.append(1)
            put(
                **{
                    "Item": {
                        **table.items["NB-1"],
                        "case_json": json.dumps(
                            {
                                **json.loads(table.items["NB-1"]["case_json"]),
                                "messages": [{"text": "hi"}],
                            }
                        ),
                    }
                }
            )
        return put(Item, **kwargs)

    table.put_item = put_after_a_message
    saved = await store.rate("NB-1", 3, "t")
    assert saved["rating"] == 3 and saved["messages"] == [{"text": "hi"}]


async def test_dynamo_rate_gives_up_with_rating_conflict_and_writes_nothing(client):
    table = FakeCasesTable()
    store = DynamoCaseStore(table, ttl_days=7)
    app.dependency_overrides[get_case_store] = lambda: store
    try:
        session_id, case_id = await open_case(store)
        client.post(f"/v1/agent/cases/{case_id}/close", json=KEY)
        before = dict(table.items[case_id])
        put = table.put_item
        attempts = []

        def always_changed(Item, **kwargs):  # case_json changes between our read and our write
            attempts.append(1)
            row = table.items[case_id]
            put(**{"Item": {**row, "case_json": row["case_json"] + " "}})
            return put(Item, **kwargs)  # fails: case_json is not what we saw, rating still unset

        table.put_item = always_changed
        with pytest.raises(RatingConflict):
            await store.rate(case_id, 4, "t")
        res = rate(client, session_id, 4)
        assert res.status_code == 409 and res.json() == {"detail": "rating_conflict"}
        assert len(attempts) == 10  # 5 retries per call, bounded
        assert "rating" not in table.items[case_id]
        assert json.loads(table.items[case_id]["case_json"]) == json.loads(before["case_json"])
    finally:
        app.dependency_overrides.pop(get_case_store, None)
