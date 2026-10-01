"""Account tools: only the verified customer's data, whatever the model asks (decision 26)."""

import json
import time
from datetime import date

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from app import agent
from app.agent.account_data import DemoAccountData, DynamoAccountData
from app.agent.account_tools import run_account_tool
from app.agent.graph import MAX_TOOL_ROUNDS, build_graph
from app.agent.identity import SESSION_CUSTOMER
from app.sessions import get_session_store


class ToolCallingFake(BaseChatModel):
    """Replies with the given messages in order, streaming their tool calls too (the stock fake
    only streams text), and records the messages it was called with."""

    replies: list
    calls: list = []

    @property
    def _llm_type(self) -> str:
        return "tool-calling-fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _next(self, messages) -> AIMessage:
        self.calls.append(messages)
        return self.replies.pop(0)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        reply = self._next(messages)
        chunks = [
            {**c, "args": json.dumps(c["args"]), "index": i} for i, c in enumerate(reply.tool_calls)
        ]
        yield ChatGenerationChunk(message=AIMessageChunk(reply.text, tool_call_chunks=chunks))


def RecordingFake(messages, calls):  # noqa: N802 - same shape as tests.test_agent.RecordingFake
    return ToolCallingFake(replies=list(messages), calls=calls)


AS_OF = date(2026, 6, 17)


class SpyData(DemoAccountData):
    """Demo data that records whose data was read."""

    def __init__(self):
        super().__init__()
        self.reads: list[tuple[str, str]] = []

    async def products(self, customer_id):
        self.reads.append(("products", customer_id))
        return await super().products(customer_id)

    async def transactions(self, customer_id, since, until):
        self.reads.append(("transactions", customer_id))
        return await super().transactions(customer_id, since, until)

    async def complaints(self, customer_id):
        self.reads.append(("complaints", customer_id))
        return await super().complaints(customer_id)


async def run(name, args=None, customer_id="demo-001", data=None):
    out = await run_account_tool(
        name, args or {}, customer_id=customer_id, data=data or DemoAccountData(), as_of=AS_OF
    )
    return json.loads(out)


# --- the tools --------------------------------------------------------------------------------


async def test_products():
    result = await run("get_my_products")
    assert [p["product_number_last4"] for p in result["products"]] == ["4521", "2209"]
    assert result["data_as_of"] == "2026-06-17"


async def test_transactions_filters_and_decline_reason():
    result = await run("get_my_transactions", {"days": 30})
    assert result["period"] == {"from": "2026-05-18", "to": "2026-06-17"}
    assert [t["merchant_name"] for t in result["transactions"]] == ["Rappi", "TecnoMundo"]

    declined = await run("get_my_transactions", {"status": "declined"})
    [t] = declined["transactions"]
    assert t["merchant_name"] == "TecnoMundo" and t["decline_reason"].startswith("insufficient")

    assert (await run("get_my_transactions", {"days": 90}))["total_found"] == 3
    assert (await run("get_my_transactions", {"days": 90, "search": "rappi"}))["total_found"] == 1
    limited = await run("get_my_transactions", {"days": 90, "limit": 1})
    assert limited["total_found"] == 3 and len(limited["transactions"]) == 1


async def test_search_understands_spanish_and_portuguese_words():
    """The data's types are English; found by the held-out report: "transferencia" found nothing."""
    for word in ("transferencia", "Transferências", "transferir", "transfer"):
        found = await run("get_my_transactions", {"days": 90, "search": word})
        assert [t["transaction_type"] for t in found["transactions"]] == ["Transfer"], word
    assert (await run("get_my_transactions", {"days": 90, "search": "compras"}))["total_found"] == 2
    assert (await run("get_my_transactions", {"days": 90, "search": "pagamento"}))[
        "total_found"
    ] == 0


async def test_transaction_arguments_are_clamped():
    result = await run("get_my_transactions", {"days": 100000, "limit": 999})
    assert result["period"]["from"] == "2025-06-17"  # at most 365 days
    assert (await run("get_my_transactions", {"days": "x"}))["error"].startswith("invalid")


async def test_complaints_by_status():
    assert len((await run("get_my_complaints", {"status": "open"}))["complaints"]) == 1
    assert (await run("get_my_complaints", {"status": "closed"}))["complaints"] == []


async def test_the_model_cant_pick_another_customer():
    spy = SpyData()
    result = await run("get_my_products", {"customer_id": "demo-002"}, data=spy)
    assert spy.reads == [("products", "demo-001")]
    assert "7788" not in json.dumps(result)  # Ana's account


async def test_unknown_tool():
    assert (await run("delete_everything"))["error"] == "unknown tool delete_everything"


# --- DynamoDB ---------------------------------------------------------------------------------


class FakeTable:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages[len(self.calls) - 1]


async def test_dynamo_transactions_are_one_partition_key_range_and_paginated():
    table = FakeTable(
        [
            {
                "Items": [{"sk": "TXN#2026-06-10#T2", "amount": 5, "is_fraud": True}],
                "LastEvaluatedKey": {"k": 1},
            },
            {"Items": [{"sk": "TXN#2026-06-01#T1", "amount": 7, "fraud_score": 0.9}]},
        ]
    )
    rows = await DynamoAccountData(table).transactions("C1", date(2026, 5, 18), AS_OF)
    assert rows == [{"amount": 5}, {"amount": 7}]  # fraud labels never leave the table
    first = table.calls[0]
    assert first["ScanIndexForward"] is False
    values = first["KeyConditionExpression"].get_expression()["values"]
    assert values[0].get_expression()["values"][1] == "C1"  # the partition: this customer only
    assert values[1].get_expression()["values"][1:] == ("TXN#2026-05-18", "TXN#2026-06-17~")
    assert table.calls[1]["ExclusiveStartKey"] == {"k": 1}


async def test_dynamo_products_keep_only_banking_app_fields():
    table = FakeTable(
        [{"Items": [{"sk": "PRODUCT#P9", "product_type": "Tarjeta", "opening_branch_id": "B1"}]}]
    )
    assert await DynamoAccountData(table).products("C1") == [
        {"product_id": "P9", "product_type": "Tarjeta"}
    ]


# --- in the graph -----------------------------------------------------------------------------


def verified_auth(customer_id="demo-001", name="Miguel"):
    return {
        "step": "verified",
        SESSION_CUSTOMER: customer_id,
        "customer_id": customer_id,
        "first_name": name,
        "verified_until": time.time() + 600,
    }


def call(name, args=None, i=1):
    return AIMessage("", tool_calls=[{"name": name, "args": args or {}, "id": f"c{i}"}])


async def chat(model, data, auth, text="¿cuál es mi saldo?"):
    store = get_session_store()
    session = await store.create("es", auth)
    agent._graph = build_graph(model, account_data=data)
    try:
        return "".join([p async for p in agent.stream_reply(session.id, text, "es")])
    finally:
        agent._graph = None


async def test_verified_customer_gets_their_data_through_the_tool():
    spy = SpyData()
    model = RecordingFake(
        messages=iter([call("get_my_products", {"customer_id": "demo-002"}), AIMessage("Listo")]),
        calls=[],
    )
    reply = await chat(model, spy, verified_auth())
    assert reply == "Listo"
    assert spy.reads == [("products", "demo-001")]
    tool_result = model.calls[1][-1]
    assert isinstance(tool_result, ToolMessage) and "4521" in tool_result.text
    assert "7788" not in tool_result.text


async def test_account_tools_before_verifying_start_verification_and_read_nothing():
    spy = SpyData()
    model = RecordingFake(messages=iter([call("get_my_products")]), calls=[])
    reply = await chat(model, spy, {})
    assert "verificar tu identidad" in reply
    assert spy.reads == []


async def test_expired_verification_reads_nothing():
    spy = SpyData()
    auth = {**verified_auth(), "verified_until": time.time() - 1}
    model = RecordingFake(messages=iter([call("get_my_products")]), calls=[])
    await chat(model, spy, auth)
    assert spy.reads == []


async def test_tool_rounds_are_capped():
    spy = SpyData()
    calls = [call("get_my_products", i=i) for i in range(MAX_TOOL_ROUNDS + 2)]
    model = RecordingFake(messages=iter(calls), calls=[])
    await chat(model, spy, verified_auth())
    assert len(spy.reads) == MAX_TOOL_ROUNDS
    assert len(model.calls) == MAX_TOOL_ROUNDS + 1  # the last call ends the turn


async def test_text_before_and_after_a_tool_call_are_separate_paragraphs():
    first = AIMessage(
        "Déjame revisar.", tool_calls=[{"name": "get_my_products", "args": {}, "id": "c1"}]
    )
    model = RecordingFake(messages=iter([first, AIMessage("Tu saldo es X.")]), calls=[])
    reply = await chat(model, SpyData(), verified_auth())
    assert reply == "Déjame revisar.\n\nTu saldo es X."


async def test_offline_model_uses_the_tools_once_verified():
    from app.fake_llm import OfflineChatModel

    spy = SpyData()
    reply = await chat(OfflineChatModel(delay_seconds=0), spy, verified_auth(), "pagos rechazados")
    assert spy.reads == [("transactions", "demo-001")]
    assert "TecnoMundo" in reply and "Rappi" not in reply  # only the declined one


# --- home page overview (POST /v1/accounts/overview) --------------------------------------------


async def test_overview_of_the_verified_customer(client):
    session = await get_session_store().create("es", verified_auth())
    r = client.post("/v1/accounts/overview", json={"session_id": session.id})
    assert r.status_code == 200
    body = r.json()
    assert body["data_as_of"] == "2026-06-17"
    assert [p["product_number_last4"] for p in body["products"]] == ["4521", "2209"]
    assert [t["merchant_name"] for t in body["recent_transactions"]] == ["Rappi", "TecnoMundo"]
    assert body["open_complaints"] == 1


async def test_overview_needs_a_verified_session(client):
    bound_only = await get_session_store().create("es", {SESSION_CUSTOMER: "demo-001"})
    expired = await get_session_store().create(
        "es", {**verified_auth(), "verified_until": time.time() - 1}
    )
    for session_id in (bound_only.id, expired.id, "nope"):
        r = client.post("/v1/accounts/overview", json={"session_id": session_id})
        assert r.status_code == 401 and r.json() == {"detail": "not_verified"}
