"""The `security` part of GET /v1/metrics/live: WAF blocks of the last 24 h (decision 50)."""

import pytest

from app import security_metrics
from app.api import metrics
from app.config import get_settings


@pytest.fixture(autouse=True)
def fresh_cache():
    metrics.clear_cache()
    yield
    metrics.clear_cache()


def _series(**sums: float) -> list[dict]:
    return [{"Id": k, "Values": [v]} for k, v in sums.items()]


def test_summarize_maps_rules_to_the_four_reasons():
    body = security_metrics.summarize(
        _series(
            allowed=900,
            blocked=100,
            rate_limits_0=10,  # site-flood
            rate_limits_1=5,
            rate_limits_5=1,  # api-flood
            unknown_routes_0=20,
            unknown_routes_1=2,
            attack_signatures_0=7,
            attack_signatures_1=3,
            bad_reputation_0=4,
        )
    )
    assert body["window_hours"] == 24
    assert body["requests"] == 1000 and body["blocked"] == 100
    assert body["by_reason"] == {
        "rate_limits": 16,
        "unknown_routes": 22,
        "attack_signatures": 10,
        "bad_reputation": 4,
    }
    assert body["generated_at"]


def test_summarize_treats_missing_series_as_zero():
    # A rule that never fired has no data points, and the whole ACL may be quiet.
    body = security_metrics.summarize([{"Id": "allowed", "Values": []}])
    assert body["requests"] == 0 and body["blocked"] == 0
    assert body["by_reason"] == dict.fromkeys(security_metrics.REASONS, 0)


def test_queries_ask_only_for_known_rules_in_one_call():
    queries = security_metrics._queries("acl")
    rules = {q["MetricStat"]["Metric"]["Dimensions"][1]["Value"] for q in queries}
    assert rules == {"ALL"} | {f"fh26-{r}" for rs in security_metrics.REASONS.values() for r in rs}
    assert not any("admin" in r for r in rules)
    assert all(q["MetricStat"]["Stat"] == "Sum" for q in queries)


async def test_fetch_is_none_when_no_web_acl():
    assert await security_metrics.fetch_security(None, "us-east-1") is None
    assert await security_metrics.fetch_security("", "us-east-1") is None


async def test_fetch_reads_cloudwatch_in_one_call(monkeypatch):
    calls = []

    class FakeCloudWatch:
        def get_metric_data(self, **kwargs):
            calls.append(kwargs)
            return {"MetricDataResults": _series(allowed=9, blocked=1, bad_reputation_0=1)}

    def fake_client(service, **kwargs):
        assert service == "cloudwatch" and kwargs["region_name"] == "us-east-1"
        return FakeCloudWatch()

    monkeypatch.setattr(security_metrics.boto3, "client", fake_client)
    body = await security_metrics.fetch_security("acl", "us-east-1")
    assert len(calls) == 1
    assert body["requests"] == 10 and body["by_reason"]["bad_reputation"] == 1


async def test_fetch_reports_unavailable_when_cloudwatch_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("no access")

    monkeypatch.setattr(security_metrics.boto3, "client", boom)
    assert await security_metrics.fetch_security("acl", "us-east-1") == {"error": "unavailable"}


def _with_web_acl(monkeypatch):
    settings = get_settings().model_copy(update={"waf_web_acl_name": "acl"})
    monkeypatch.setattr(metrics, "get_settings", lambda: settings)


def test_endpoint_security_is_null_when_unset(client):
    res = client.get("/v1/metrics/live")
    assert res.status_code == 200 and res.json()["security"] is None


def test_endpoint_includes_security_numbers(client, monkeypatch):
    _with_web_acl(monkeypatch)
    seen = []

    async def fake(web_acl, region):
        seen.append((web_acl, region))
        return security_metrics.summarize(_series(allowed=5, blocked=2, rate_limits_0=2))

    monkeypatch.setattr(metrics, "fetch_security", fake)
    body = client.get("/v1/metrics/live").json()
    assert seen == [("acl", "us-east-1")]
    assert body["security"]["blocked"] == 2 and body["security"]["by_reason"]["rate_limits"] == 2


def test_endpoint_still_200_when_cloudwatch_fails(client, monkeypatch):
    _with_web_acl(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("no access")

    monkeypatch.setattr(security_metrics.boto3, "client", boom)
    res = client.get("/v1/metrics/live")
    assert res.status_code == 200
    body = res.json()
    assert body["security"] == {"error": "unavailable"}
    assert "turns" in body
