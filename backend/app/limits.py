"""Spend limits for the public chat: a daily budget for the whole app and a per-visitor rate limit.

The budget is checked before calling the model and charged after each turn with the tokens the
model reported, so concurrent turns can overshoot it by a few cents at most. Deployed, the
counters live in the interactions table (partition key "#limits"), updated atomically.
"""

import asyncio
import hashlib
import ipaddress
import time
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Literal, Protocol

from app.config import Settings, get_settings

LimitCode = Literal["rate_limited", "daily_budget_exhausted"]

LIMITS_PARTITION = "#limits"
MICRO_USD = 1_000_000  # the budget is counted in millionths of a dollar (integers)


class CounterStore(Protocol):
    async def add(self, key: str, amount: int, *, below: int | None, ttl_seconds: int) -> bool:
        """Add `amount` to the counter. With `below`, only if the counter is still under it;
        returns False (and adds nothing) when it isn't."""
        ...


class MemoryCounterStore:
    """Process-local counters: local development and tests."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}

    async def add(self, key: str, amount: int, *, below: int | None, ttl_seconds: int) -> bool:
        current = self.counters.get(key, 0)
        if below is not None and current >= below:
            return False
        self.counters[key] = current + amount
        return True


class DynamoCounterStore:
    """Deployed: atomic conditional updates, one item per counter, expiring through TTL."""

    def __init__(self, table: Any) -> None:
        self.table = table  # boto3 DynamoDB Table resource (the interactions table)

    def _add(self, key: str, amount: int, below: int | None, ttl_seconds: int) -> bool:
        from botocore.exceptions import ClientError

        params: dict[str, Any] = {
            "Key": {"session_id": LIMITS_PARTITION, "message_id": key},
            "UpdateExpression": "ADD #v :amount SET expires_at = if_not_exists(expires_at, :exp)",
            "ExpressionAttributeNames": {"#v": "value"},
            "ExpressionAttributeValues": {
                ":amount": amount,
                ":exp": int(time.time()) + ttl_seconds,
            },
        }
        if below is not None:
            params["ConditionExpression"] = "attribute_not_exists(#v) OR #v < :below"
            params["ExpressionAttributeValues"][":below"] = below
        try:
            self.table.update_item(**params)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True

    async def add(self, key: str, amount: int, *, below: int | None, ttl_seconds: int) -> bool:
        return await asyncio.to_thread(self._add, key, amount, below, ttl_seconds)


class Limiter:
    def __init__(self, settings: Settings, store: CounterStore) -> None:
        self.store = store
        self.rate_limit = settings.rate_limit_per_hour
        self.budget = (
            round(settings.daily_budget_usd * MICRO_USD)
            if settings.daily_budget_usd is not None
            else None
        )
        self.price_in = settings.llm_price_input_per_mtok
        self.price_out = settings.llm_price_output_per_mtok

    @staticmethod
    def _day() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    async def check(self, client_ip: str | None) -> LimitCode | None:
        """Call before a turn. Returns why the turn is refused, or None to go ahead."""
        if self.budget is not None:
            # Adding 0 only checks: fails once the day's spend reached the budget.
            if not await self.store.add(
                f"budget#{self._day()}", 0, below=self.budget, ttl_seconds=2 * 86400
            ):
                return "daily_budget_exhausted"
        if self.rate_limit is not None and client_ip:
            hour = datetime.now(UTC).strftime("%Y-%m-%dT%H")
            # Visitors are counted by a hash of their IP; the IP itself is never stored.
            visitor = hashlib.sha256(visitor_key(client_ip).encode()).hexdigest()[:16]
            if not await self.store.add(
                f"rate#{visitor}#{hour}", 1, below=self.rate_limit, ttl_seconds=2 * 3600
            ):
                return "rate_limited"
        return None

    def cost_micro_usd(self, input_tokens: int | None, output_tokens: int | None) -> int:
        dollars = (input_tokens or 0) * self.price_in + (output_tokens or 0) * self.price_out
        return round(dollars)  # tokens x $/million tokens = millionths of a dollar

    async def charge(self, input_tokens: int | None, output_tokens: int | None) -> None:
        """Call after a turn with the tokens the model reported."""
        cost = self.cost_micro_usd(input_tokens, output_tokens)
        if self.budget is not None and cost > 0:
            await self.store.add(f"budget#{self._day()}", cost, below=None, ttl_seconds=2 * 86400)


def visitor_key(client_ip: str) -> str:
    """What one visitor is. An IPv4 address, or the /64 network of an IPv6 one: a single
    connection usually owns a whole /64, so counting each IPv6 address apart would let one
    visitor rotate addresses past the limit."""
    try:
        address = ipaddress.ip_address(client_ip.strip("[]"))
    except ValueError:
        return client_ip
    if address.version == 6 and address.ipv4_mapped:  # "::ffff:203.0.113.7" is an IPv4 visitor
        return str(address.ipv4_mapped)
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def client_ip_from(headers: Any, fallback: str | None) -> str | None:
    """The visitor's IP. Behind CloudFront, CloudFront-Viewer-Address ("ip:port") is set by
    CloudFront itself, so visitors can't fake it; locally, the socket's address."""
    address = headers.get("cloudfront-viewer-address")
    if address:
        return address.rsplit(":", 1)[0]
    return fallback


def build_limiter(settings: Settings) -> Limiter:
    if settings.interactions_store == "dynamodb":
        import boto3

        table = boto3.resource("dynamodb", region_name=settings.aws_region).Table(
            settings.interactions_table
        )
        return Limiter(settings, DynamoCounterStore(table))
    return Limiter(settings, MemoryCounterStore())


@lru_cache
def get_limiter() -> Limiter:
    return build_limiter(get_settings())
