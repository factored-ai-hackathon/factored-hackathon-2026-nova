"""Interaction records: one per chat turn, plus the customer's feedback on the reply.

Used to measure the assistant (latency, tokens, errors, ratings) and to turn bad replies into
new eval cases. Text is masked before it is stored. See docs/api-contract.md.
"""

import asyncio
import json
import math
import re
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Protocol

from app.config import Settings, get_settings

Rating = Literal["up", "down"]

# 8+ digits, optionally split by spaces or dashes: card and account numbers. Shorter numbers
# (amounts, dates) are kept. Only the last 4 digits survive.
_LONG_NUMBER = re.compile(r"\d(?:[ -]?\d){7,}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def mask_pii(text: str) -> str:
    def last4(m: re.Match[str]) -> str:
        return "****" + re.sub(r"\D", "", m.group())[-4:]

    return _EMAIL.sub("[email]", _LONG_NUMBER.sub(last4, text))


@dataclass
class Turn:
    session_id: str
    message_id: str
    lang: str
    user_text: str
    reply_text: str
    status: Literal["ok", "error"]
    error_code: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    first_token_ms: int | None = None
    total_ms: int | None = None
    intent: str | None = None  # the intent classifier's label (app/agent/intent.py)
    intent_confidence: float | None = None
    created_at: str = ""
    channel: str = "account"  # "public" for the assistant outside the login

    def __post_init__(self) -> None:
        self.created_at = self.created_at or datetime.now(UTC).isoformat()

    def masked(self) -> "Turn":
        return Turn(
            **{
                **asdict(self),
                "user_text": mask_pii(self.user_text),
                "reply_text": mask_pii(self.reply_text),
            }
        )

    def metrics(self) -> dict[str, Any]:
        """The numbers only, no text: safe for application logs."""
        record = asdict(self)
        del record["user_text"], record["reply_text"]
        return record


# --- live aggregates (GET /v1/metrics/live) ------------------------------------------------------

# The only fields read to aggregate turns: numbers and labels, never the text. session_id is read
# to count distinct conversations and is never returned.
AGGREGATE_FIELDS = (
    "session_id",
    "status",
    "lang",
    "channel",
    "input_tokens",
    "output_tokens",
    "first_token_ms",
    "total_ms",
    "intent",
    "intent_confidence",
    "created_at",
    "type",
)


def is_turn_record(record: dict[str, Any]) -> bool:
    """Turn items only: not audit entries ("type": "audit"), JSONL feedback lines ("type":
    "feedback") or the spend-limit counters (partition "#limits", no status)."""
    return record.get("type") in (None, "turn") and record.get("status") in ("ok", "error")


def _percentile(values: list[int], q: float) -> int | None:
    """Nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float | Decimal) else None


@dataclass
class TurnAggregate:
    """Running totals over turn records; summary() is aggregates only (no text, no ids)."""

    turns: int = 0
    errors: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    first: str | None = None
    last: str | None = None
    sessions: set[str] = field(default_factory=set)
    total_ms: list[int] = field(default_factory=list)
    first_token_ms: list[int] = field(default_factory=list)
    intents: Counter = field(default_factory=Counter)
    confident: int = 0
    by_lang: dict[str, tuple[int, set[str]]] = field(default_factory=dict)
    by_channel: dict[str, tuple[int, set[str]]] = field(default_factory=dict)

    def add(self, record: dict[str, Any], threshold: float) -> None:
        if not is_turn_record(record):
            return
        session = str(record.get("session_id", ""))
        self.turns += 1
        self.sessions.add(session)
        if record.get("status") == "error":
            self.errors += 1
        self.input_tokens += int(_num(record.get("input_tokens")) or 0)
        self.output_tokens += int(_num(record.get("output_tokens")) or 0)
        for key, values in (("total_ms", self.total_ms), ("first_token_ms", self.first_token_ms)):
            if (v := _num(record.get(key))) is not None:
                values.append(int(v))
        if created := record.get("created_at"):
            self.first = min(self.first or created, created)
            self.last = max(self.last or created, created)
        if intent := record.get("intent"):
            self.intents[str(intent)] += 1
            confidence = _num(record.get("intent_confidence"))
            if confidence is not None and confidence >= threshold:
                self.confident += 1
        for groups, key, default in (
            (self.by_lang, "lang", "unknown"),
            (self.by_channel, "channel", "account"),
        ):
            name = str(record.get(key) or default)
            count, ids = groups.get(name, (0, set()))
            ids.add(session)
            groups[name] = (count + 1, ids)

    def summary(self, price_in: float, price_out: float, threshold: float) -> dict[str, Any]:
        """Prices are dollars per million tokens (app/config.py)."""
        conversations = len(self.sessions)
        cost = (self.input_tokens * price_in + self.output_tokens * price_out) / 1_000_000
        classified = sum(self.intents.values())

        def per_conversation(value: float, digits: int) -> float | None:
            return round(value / conversations, digits) if conversations else None

        def groups(g: dict[str, tuple[int, set[str]]]) -> dict[str, dict[str, int]]:
            return {k: {"turns": n, "conversations": len(ids)} for k, (n, ids) in sorted(g.items())}

        return {
            "turns": self.turns,
            "conversations": conversations,
            "window": {"first": self.first, "last": self.last},
            "errors": self.errors,
            "error_rate": round(self.errors / self.turns, 4) if self.turns else None,
            "tokens": {
                "input_per_conversation": per_conversation(self.input_tokens, 1),
                "output_per_conversation": per_conversation(self.output_tokens, 1),
            },
            "cost": {
                "per_conversation": per_conversation(cost, 6),
                "per_1000_conversations": per_conversation(cost * 1000, 4),
                "per_1000_turns": round(cost * 1000 / self.turns, 4) if self.turns else None,
                "price_per_mtok": {"input": price_in, "output": price_out},
            },
            "latency_ms": {
                key: {"p50": _percentile(v, 0.5), "p95": _percentile(v, 0.95), "n": len(v)}
                for key, v in (("total", self.total_ms), ("first_token", self.first_token_ms))
            },
            "intent": {
                "classified": classified,
                "distribution": dict(self.intents.most_common()),
                "confident_share": round(self.confident / classified, 4) if classified else None,
                "threshold": threshold,
            },
            "by_lang": groups(self.by_lang),
            "by_channel": groups(self.by_channel),
        }


class InteractionStore(Protocol):
    async def save_turn(self, turn: Turn) -> None: ...

    async def save_audit(self, session_id: str, message_id: str, entries: list[dict]) -> None:
        """The audit entries of a turn (app/audit.py): no text, no raw arguments, no customer id."""
        ...

    async def set_feedback(
        self, session_id: str, message_id: str, rating: Rating, comment: str | None
    ) -> bool:
        """Attach feedback to a recorded turn. Returns False if the turn is unknown."""
        ...

    async def aggregate(self, threshold: float) -> TurnAggregate:
        """Aggregates over every stored turn (numbers and labels only, see AGGREGATE_FIELDS)."""
        ...


class NoopInteractionStore:
    async def save_turn(self, turn: Turn) -> None:
        return None

    async def save_audit(self, session_id: str, message_id: str, entries: list[dict]) -> None:
        return None

    async def set_feedback(self, *args: Any) -> bool:
        return False

    async def aggregate(self, threshold: float) -> TurnAggregate:
        return TurnAggregate()


class MemoryInteractionStore:
    """Process-local store, for tests."""

    def __init__(self) -> None:
        self.turns: dict[tuple[str, str], dict[str, Any]] = {}
        self.audit: list[dict[str, Any]] = []

    async def save_turn(self, turn: Turn) -> None:
        self.turns[(turn.session_id, turn.message_id)] = asdict(turn.masked())

    async def save_audit(self, session_id: str, message_id: str, entries: list[dict]) -> None:
        self.audit += [{**e, "session_id": session_id, "message_id": message_id} for e in entries]

    async def set_feedback(
        self, session_id: str, message_id: str, rating: Rating, comment: str | None
    ) -> bool:
        record = self.turns.get((session_id, message_id))
        if record is None:
            return False
        record.update(feedback=rating, feedback_comment=comment)
        return True

    async def aggregate(self, threshold: float) -> TurnAggregate:
        agg = TurnAggregate()
        for record in self.turns.values():
            agg.add({k: record.get(k) for k in AGGREGATE_FIELDS}, threshold)
        return agg


class JsonlInteractionStore:
    """Local development: appends turn and feedback records to a JSONL file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _append(self, record: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _has_turn(self, session_id: str, message_id: str) -> bool:
        if not self.path.exists():
            return False
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if (
                    r.get("type") == "turn"
                    and r["session_id"] == session_id
                    and r["message_id"] == message_id
                ):
                    return True
        return False

    async def save_turn(self, turn: Turn) -> None:
        await asyncio.to_thread(self._append, {"type": "turn", **asdict(turn.masked())})

    async def save_audit(self, session_id: str, message_id: str, entries: list[dict]) -> None:
        for e in entries:
            record = {"type": "audit", "session_id": session_id, "message_id": message_id, **e}
            await asyncio.to_thread(self._append, record)

    async def set_feedback(
        self, session_id: str, message_id: str, rating: Rating, comment: str | None
    ) -> bool:
        if not await asyncio.to_thread(self._has_turn, session_id, message_id):
            return False
        record = {
            "type": "feedback",
            "session_id": session_id,
            "message_id": message_id,
            "feedback": rating,
            "feedback_comment": mask_pii(comment) if comment else None,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await asyncio.to_thread(self._append, record)
        return True

    def _aggregate(self, threshold: float) -> TurnAggregate:
        agg = TurnAggregate()
        if not self.path.exists():
            return agg
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                agg.add({k: record.get(k) for k in AGGREGATE_FIELDS}, threshold)
        return agg

    async def aggregate(self, threshold: float) -> TurnAggregate:
        return await asyncio.to_thread(self._aggregate, threshold)


class DynamoInteractionStore:
    """Deployed: one item per turn (PK session_id, SK message_id), expiring through TTL."""

    def __init__(self, table: Any, ttl_days: int) -> None:
        self.table = table  # boto3 DynamoDB Table resource
        self.ttl_days = ttl_days

    async def save_turn(self, turn: Turn) -> None:
        item = {k: v for k, v in asdict(turn.masked()).items() if v is not None}
        # boto3 rejects floats: DynamoDB numbers go as Decimal.
        item = {k: Decimal(str(v)) if isinstance(v, float) else v for k, v in item.items()}
        item["expires_at"] = int(time.time()) + self.ttl_days * 86400
        await asyncio.to_thread(self.table.put_item, Item=item)

    async def save_audit(self, session_id: str, message_id: str, entries: list[dict]) -> None:
        # Same table and expiry as the turns; the sort key says whose audit entry it is.
        expires = int(time.time()) + self.ttl_days * 86400
        for i, e in enumerate(entries):
            item = {
                **e,
                "type": "audit",
                "session_id": session_id,
                "message_id": f"{message_id}#audit{i:02d}",
                "expires_at": expires,
            }
            await asyncio.to_thread(self.table.put_item, Item=item)

    async def set_feedback(
        self, session_id: str, message_id: str, rating: Rating, comment: str | None
    ) -> bool:
        from botocore.exceptions import ClientError

        try:
            await asyncio.to_thread(
                self.table.update_item,
                Key={"session_id": session_id, "message_id": message_id},
                UpdateExpression="SET feedback = :r, feedback_comment = :c, feedback_at = :t",
                ConditionExpression="attribute_exists(message_id)",
                ExpressionAttributeValues={
                    ":r": rating,
                    ":c": mask_pii(comment) if comment else None,
                    ":t": datetime.now(UTC).isoformat(),
                },
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True

    def _aggregate(self, threshold: float) -> TurnAggregate:
        # A paginated Scan that reads only the numeric and label attributes (never the text).
        # Attribute names go through placeholders: several are DynamoDB reserved words.
        names = {f"#a{i}": name for i, name in enumerate(AGGREGATE_FIELDS)}
        params: dict[str, Any] = {
            "ProjectionExpression": ", ".join(names),
            "ExpressionAttributeNames": names,
        }
        agg = TurnAggregate()
        while True:
            page = self.table.scan(**params)
            for item in page.get("Items", []):
                agg.add(item, threshold)
            if "LastEvaluatedKey" not in page:
                return agg
            params["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    async def aggregate(self, threshold: float) -> TurnAggregate:
        return await asyncio.to_thread(self._aggregate, threshold)


def build_interaction_store(settings: Settings) -> InteractionStore:
    if settings.interactions_store == "none":
        return NoopInteractionStore()
    if settings.interactions_store == "dynamodb":
        import boto3

        table = boto3.resource("dynamodb", region_name=settings.aws_region).Table(
            settings.interactions_table
        )
        return DynamoInteractionStore(table, settings.interactions_ttl_days)
    return JsonlInteractionStore(settings.interactions_path)


@lru_cache
def get_interaction_store() -> InteractionStore:
    return build_interaction_store(get_settings())
