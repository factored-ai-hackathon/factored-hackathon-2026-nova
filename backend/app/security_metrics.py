"""What the edge firewall blocked in the last 24 hours, for /models (decision 50).

One CloudWatch `GetMetricData` call reads the web ACL's counters (the metrics live in us-east-1
because the ACL's scope is CLOUDFRONT). Only numbers leave: no IPs, no request samples, no rule
internals. Count-only and allow rules are never queried.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from botocore.config import Config

WINDOW_HOURS = 24

# Reason shown on the page -> the WAF rules whose blocks it adds up (metric name is fh26-<rule>).
REASONS: dict[str, tuple[str, ...]] = {
    "rate_limits": (
        "site-flood",
        "live-per-ip",
        "auth-per-ip",
        "demo-per-ip",
        "api-per-ip",
        "api-flood",
    ),
    "unknown_routes": ("api-unknown-route", "api-body-too-large"),
    "attack_signatures": ("known-bad-inputs", "common-rules"),
    "bad_reputation": ("ip-reputation",),
}


def _query(web_acl: str, qid: str, rule: str, metric: str) -> dict[str, Any]:
    dims = [{"Name": "WebACL", "Value": web_acl}, {"Name": "Rule", "Value": rule}]
    return {
        "Id": qid,
        "MetricStat": {
            "Metric": {"Namespace": "AWS/WAFV2", "MetricName": metric, "Dimensions": dims},
            "Period": WINDOW_HOURS * 3600,
            "Stat": "Sum",
        },
        "ReturnData": True,
    }


def _queries(web_acl: str) -> list[dict[str, Any]]:
    queries = [
        _query(web_acl, "allowed", "ALL", "AllowedRequests"),
        _query(web_acl, "blocked", "ALL", "BlockedRequests"),
    ]
    for reason, rules in REASONS.items():
        for i, rule in enumerate(rules):
            queries.append(_query(web_acl, f"{reason}_{i}", f"fh26-{rule}", "BlockedRequests"))
    return queries


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Turn GetMetricData results into the `security` body; a series with no data counts as 0."""
    sums = {r["Id"]: sum(r.get("Values", [])) for r in results}
    allowed, blocked = sums.get("allowed", 0), sums.get("blocked", 0)
    by_reason = {
        reason: int(sum(sums.get(f"{reason}_{i}", 0) for i in range(len(rules))))
        for reason, rules in REASONS.items()
    }
    return {
        "window_hours": WINDOW_HOURS,
        "requests": int(allowed + blocked),
        "blocked": int(blocked),
        "by_reason": by_reason,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _read(web_acl: str, region: str) -> dict[str, Any]:
    client = boto3.client(
        "cloudwatch",
        region_name=region,
        config=Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 1}),
    )
    end = datetime.now(UTC)
    res = client.get_metric_data(
        MetricDataQueries=_queries(web_acl),
        StartTime=end - timedelta(hours=WINDOW_HOURS),
        EndTime=end,
    )
    return summarize(res["MetricDataResults"])


async def fetch_security(web_acl: str | None, region: str) -> dict[str, Any] | None:
    """`None` if no web ACL is configured (local, tests); `{"error": "unavailable"}` on failure."""
    if not web_acl:
        return None
    try:
        return await asyncio.to_thread(_read, web_acl, region)
    except Exception:  # never let CloudWatch break the endpoint
        return {"error": "unavailable"}
