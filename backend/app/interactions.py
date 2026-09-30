"""Interaction records: one per chat turn, plus the customer's feedback on the reply.

Used to measure the assistant (latency, tokens, errors, ratings) and to turn bad replies into
new eval cases. Text is masked before it is stored. See docs/api-contract.md.
"""

import asyncio
import json
import re
import threading
import time
from dataclasses import asdict, dataclass
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


class InteractionStore(Protocol):
    async def save_turn(self, turn: Turn) -> None: ...

    async def set_feedback(
        self, session_id: str, message_id: str, rating: Rating, comment: str | None
    ) -> bool:
        """Attach feedback to a recorded turn. Returns False if the turn is unknown."""
        ...


class NoopInteractionStore:
    async def save_turn(self, turn: Turn) -> None:
        return None

    async def set_feedback(self, *args: Any) -> bool:
        return False


class MemoryInteractionStore:
    """Process-local store, for tests."""

    def __init__(self) -> None:
        self.turns: dict[tuple[str, str], dict[str, Any]] = {}

    async def save_turn(self, turn: Turn) -> None:
        self.turns[(turn.session_id, turn.message_id)] = asdict(turn.masked())

    async def set_feedback(
        self, session_id: str, message_id: str, rating: Rating, comment: str | None
    ) -> bool:
        record = self.turns.get((session_id, message_id))
        if record is None:
            return False
        record.update(feedback=rating, feedback_comment=comment)
        return True


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
