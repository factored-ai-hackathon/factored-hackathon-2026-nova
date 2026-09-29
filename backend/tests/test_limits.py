import pytest
from botocore.exceptions import ClientError

from app.config import Settings
from app.limits import (
    DynamoCounterStore,
    Limiter,
    MemoryCounterStore,
    client_ip_from,
    get_limiter,
)
from app.main import app
from tests.conftest import parse_sse


def limiter(**settings) -> Limiter:
    return Limiter(Settings(_env_file=None, **settings), MemoryCounterStore())


# --- limiter ---------------------------------------------------------------------


async def test_no_limits_by_default():
    lim = limiter()
    for _ in range(100):
        assert await lim.check("1.2.3.4") is None


async def test_rate_limit_per_visitor():
    lim = limiter(rate_limit_per_hour=3)
    assert [await lim.check("1.2.3.4") for _ in range(4)] == [None, None, None, "rate_limited"]
    assert await lim.check("5.6.7.8") is None  # another visitor has their own count
    assert not any("1.2.3.4" in key for key in lim.store.counters)  # IPs are hashed


async def test_daily_budget_is_charged_with_real_tokens():
    lim = limiter(daily_budget_usd=0.01)  # 10,000 micro-dollars
    assert lim.cost_micro_usd(1_000, 1_000) == 6_000  # $1/M in + $5/M out
    assert await lim.check(None) is None
    await lim.charge(1_000, 1_000)
    assert await lim.check(None) is None  # $0.006 spent, under $0.01
    await lim.charge(1_000, 1_000)
    assert await lim.check(None) == "daily_budget_exhausted"  # $0.012 spent


def test_client_ip_prefers_cloudfront_header():
    assert client_ip_from({"cloudfront-viewer-address": "203.0.113.7:54321"}, "10.0.0.1") == (
        "203.0.113.7"
    )
    assert client_ip_from({"cloudfront-viewer-address": "2001:db8::1:443"}, None) == "2001:db8::1"
    assert client_ip_from({}, "10.0.0.1") == "10.0.0.1"


# --- DynamoDB counters (fake table that honours the condition) ---------------------


class FakeTable:
    def __init__(self):
        self.items = {}
        self.calls = []

    def update_item(self, Key, ExpressionAttributeValues, ConditionExpression=None, **kwargs):
        self.calls.append(Key)
        k = (Key["session_id"], Key["message_id"])
        current = self.items.get(k, 0)
        below = ExpressionAttributeValues.get(":below")
        if ConditionExpression and current >= below:
            error = {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}}
            raise ClientError(error, "UpdateItem")
        self.items[k] = current + ExpressionAttributeValues[":amount"]


async def test_dynamo_counters():
    table = FakeTable()
    store = DynamoCounterStore(table)
    assert await store.add("rate#x", 1, below=2, ttl_seconds=60)
    assert await store.add("rate#x", 1, below=2, ttl_seconds=60)
    assert not await store.add("rate#x", 1, below=2, ttl_seconds=60)
    assert await store.add("budget#d", 500, below=None, ttl_seconds=60)
    assert table.items == {("#limits", "rate#x"): 2, ("#limits", "budget#d"): 500}


# --- API -------------------------------------------------------------------------------


@pytest.fixture
def with_limiter():
    def _set(lim: Limiter) -> Limiter:
        app.dependency_overrides[get_limiter] = lambda: lim
        return lim

    yield _set
    app.dependency_overrides.pop(get_limiter, None)


def post(client, sid, headers=None):
    return client.post(
        f"/v1/chat/sessions/{sid}/messages", json={"text": "hola"}, headers=headers or {}
    )


def test_api_rate_limit_returns_429_without_calling_the_model(client, with_limiter, interactions):
    with_limiter(limiter(rate_limit_per_hour=2))
    sid = client.post("/v1/chat/sessions").json()["session_id"]
    viewer = {"CloudFront-Viewer-Address": "198.51.100.9:1234"}
    assert post(client, sid, viewer).status_code == 200
    assert post(client, sid, viewer).status_code == 200
    r = post(client, sid, viewer)
    assert (r.status_code, r.json()) == (429, {"detail": "rate_limited"})
    assert len(interactions.turns) == 2  # the refused message never reached the model
    assert post(client, sid, {"CloudFront-Viewer-Address": "198.51.100.10:1"}).status_code == 200


def test_api_daily_budget(client, with_limiter):
    # echo_reply reports 10 input + 3 output tokens = 25 micro-dollars per turn
    with_limiter(limiter(daily_budget_usd=0.00005))
    sid = client.post("/v1/chat/sessions").json()["session_id"]
    assert parse_sse(post(client, sid).text)[-1][0] == "done"  # 25 spent
    assert parse_sse(post(client, sid).text)[-1][0] == "done"  # 50 spent
    r = post(client, sid)
    assert (r.status_code, r.json()) == (429, {"detail": "daily_budget_exhausted"})
