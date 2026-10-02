"""GET /v1/metrics/live: aggregates over the stored turns, no text and no ids (decision 42)."""

import json

import pytest

from app.api import metrics
from app.interactions import (
    AGGREGATE_FIELDS,
    DynamoInteractionStore,
    JsonlInteractionStore,
    MemoryInteractionStore,
    TurnAggregate,
)
from tests.test_interactions import make_turn

THRESHOLD = 0.58


@pytest.fixture(autouse=True)
def fresh_cache():
    metrics.clear_cache()
    yield
    metrics.clear_cache()


async def _fill(store) -> None:
    await store.save_turn(
        make_turn(
            session_id="s1",
            message_id="m1",
            intent="complaint",
            intent_confidence=0.9,
            created_at="2026-10-01T10:00:00+00:00",
        )
    )
    await store.save_turn(
        make_turn(
            session_id="s1",
            message_id="m2",
            intent="other",
            intent_confidence=0.3,
            input_tokens=30,
            output_tokens=15,
            total_ms=1500,
            first_token_ms=300,
            created_at="2026-10-01T10:01:00+00:00",
        )
    )
    await store.save_turn(
        make_turn(
            session_id="s2",
            message_id="m1",
            lang="pt",
            channel="public",
            status="error",
            error_code="model_error",
            input_tokens=None,
            output_tokens=None,
            first_token_ms=None,
            total_ms=None,
            created_at="2026-10-02T09:00:00+00:00",
        )
    )
    await store.save_audit("s1", "m1", [{"event": "tool_call", "outcome": "ok"}])
    await store.set_feedback("s1", "m1", "up", None)


def _check(summary: dict) -> None:
    assert summary["turns"] == 3
    assert summary["conversations"] == 2
    assert summary["errors"] == 1
    assert summary["window"] == {
        "first": "2026-10-01T10:00:00+00:00",
        "last": "2026-10-02T09:00:00+00:00",
    }
    # 40 input + 20 output tokens over 2 conversations, at $1 / $5 per million.
    assert summary["tokens"] == {"input_per_conversation": 20.0, "output_per_conversation": 10.0}
    cost = (40 * 1 + 20 * 5) / 1_000_000
    assert summary["cost"]["per_conversation"] == pytest.approx(cost / 2)
    assert summary["cost"]["per_1000_conversations"] == pytest.approx(cost * 1000 / 2, abs=1e-4)
    assert summary["cost"]["per_1000_turns"] == pytest.approx(cost * 1000 / 3, abs=1e-4)
    assert summary["latency_ms"]["total"] == {"p50": 900, "p95": 1500, "n": 2}
    assert summary["latency_ms"]["first_token"] == {"p50": 120, "p95": 300, "n": 2}
    assert summary["intent"]["distribution"] == {"complaint": 1, "other": 1}
    assert summary["intent"]["confident_share"] == 0.5
    assert summary["by_lang"] == {
        "es": {"turns": 2, "conversations": 1},
        "pt": {"turns": 1, "conversations": 1},
    }
    assert summary["by_channel"] == {
        "account": {"turns": 2, "conversations": 1},
        "public": {"turns": 1, "conversations": 1},
    }


async def test_memory_store_aggregates_turns_only():
    store = MemoryInteractionStore()
    await _fill(store)
    _check((await store.aggregate(THRESHOLD)).summary(1.0, 5.0, THRESHOLD))


async def test_jsonl_store_skips_audit_and_feedback_lines(tmp_path):
    store = JsonlInteractionStore(tmp_path / "interactions.jsonl")
    await _fill(store)
    _check((await store.aggregate(THRESHOLD)).summary(1.0, 5.0, THRESHOLD))


async def test_jsonl_store_without_file(tmp_path):
    agg = await JsonlInteractionStore(tmp_path / "none.jsonl").aggregate(THRESHOLD)
    summary = agg.summary(1.0, 5.0, THRESHOLD)
    assert summary["turns"] == 0 and summary["cost"]["per_conversation"] is None
    assert summary["latency_ms"]["total"] == {"p50": None, "p95": None, "n": 0}


class ScanTable:
    """Fake table: returns its items two per page and records the scan parameters."""

    def __init__(self, items):
        self.items = items
        self.calls = []

    def scan(self, **params):
        self.calls.append(params)
        start = params.get("ExclusiveStartKey", 0)
        page = {"Items": self.items[start : start + 2]}
        if start + 2 < len(self.items):
            page["LastEvaluatedKey"] = start + 2
        return page


async def test_dynamo_store_scans_every_page_projecting_only_numbers_and_labels():
    from decimal import Decimal

    items = [
        {
            "session_id": "s1",
            "status": "ok",
            "input_tokens": Decimal(10),
            "output_tokens": Decimal(5),
            "total_ms": Decimal(900),
            "intent": "complaint",
            "intent_confidence": Decimal("0.9"),
            "lang": "es",
            "channel": "account",
            "created_at": "2026-10-01T10:00:00+00:00",
        },
        {"session_id": "s1", "type": "audit", "event": "tool_call"},
        {"session_id": "#limits", "value": Decimal(42)},
        {
            "session_id": "s2",
            "status": "error",
            "lang": "pt",
            "channel": "public",
            "created_at": "2026-10-02T09:00:00+00:00",
        },
        {
            "session_id": "s2",
            "status": "ok",
            "input_tokens": Decimal(30),
            "lang": "pt",
            "channel": "public",
            "created_at": "2026-10-02T09:01:00+00:00",
        },
    ]
    table = ScanTable(items)
    agg = await DynamoInteractionStore(table, ttl_days=30).aggregate(THRESHOLD)
    summary = agg.summary(1.0, 5.0, THRESHOLD)
    assert len(table.calls) == 3
    projected = set(table.calls[0]["ExpressionAttributeNames"].values())
    assert projected == set(AGGREGATE_FIELDS)
    assert "user_text" not in projected and "reply_text" not in projected
    assert summary["turns"] == 3 and summary["conversations"] == 2 and summary["errors"] == 1
    assert summary["tokens"]["input_per_conversation"] == 20.0
    assert summary["intent"]["confident_share"] == 1.0


def test_percentiles_use_nearest_rank():
    agg = TurnAggregate()
    for i, ms in enumerate(range(100, 2100, 100)):  # 20 turns: 100..2000 ms
        agg.add({"session_id": f"s{i}", "status": "ok", "total_ms": ms}, THRESHOLD)
    latency = agg.summary(1.0, 5.0, THRESHOLD)["latency_ms"]["total"]
    assert latency == {"p50": 1000, "p95": 1900, "n": 20}


# --- endpoint -------------------------------------------------------------------------------------


async def test_endpoint_returns_aggregates_without_text_or_ids(client, interactions):
    await _fill(interactions)
    res = client.get("/v1/metrics/live")
    assert res.status_code == 200
    body = res.json()
    _check(body)
    assert body["cache_seconds"] == 60 and body["generated_at"]
    assert body["intent"]["threshold"] == pytest.approx(THRESHOLD)
    raw = json.dumps(body)
    for leaked in ("s1", "s2", "m1", "m2", "tarjeta", "Revisaré", "test-model"):
        assert leaked not in raw


async def test_endpoint_caches_for_a_minute(client, interactions, monkeypatch):
    calls = []
    original = interactions.aggregate

    async def counting(threshold):
        calls.append(threshold)
        return await original(threshold)

    monkeypatch.setattr(interactions, "aggregate", counting)
    now = [1000.0]
    monkeypatch.setattr(metrics.time, "monotonic", lambda: now[0])

    assert client.get("/v1/metrics/live").json()["turns"] == 0
    await interactions.save_turn(make_turn())
    now[0] += 30
    assert client.get("/v1/metrics/live").json()["turns"] == 0  # still the cached one
    now[0] += 31
    assert client.get("/v1/metrics/live").json()["turns"] == 1
    assert len(calls) == 2


def test_endpoint_with_no_store(client):
    from app.interactions import NoopInteractionStore, get_interaction_store
    from app.main import app

    app.dependency_overrides[get_interaction_store] = NoopInteractionStore
    body = client.get("/v1/metrics/live").json()
    assert body["turns"] == 0 and body["window"] == {"first": None, "last": None}
