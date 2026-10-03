"""Handoff to a human agent (decision 27).

The model decides *when* (the request_human_agent tool, with its own summary of the request and
the open questions); code builds the case the human receives: the verified facts come from the
session's verification state and the evidence from the account tools this conversation actually
ran, never from the model's words. While a case is open the bot stays out: the customer's
messages go to the human (graph node human_queue), and the human's replies reach the customer's
chat (app/api/agent_console.py).
"""

import asyncio
import json
import secrets
import time
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Literal, Protocol

from botocore.exceptions import ClientError
from langchain_core.tools import tool

HANDOFF_TOOL = "request_human_agent"

Reason = Literal[
    "customer_request",
    "fraud_or_security",
    "dispute",
    "complaint",
    "unsupported",
    "repeated_failure",
    "other",
]
OPEN_STATUSES = ("waiting", "active")
STATUSES = ("waiting", "active", "closed")
MAX_EVIDENCE = 10  # tool results kept per conversation
MAX_EVIDENCE_CHARS = 1500
MAX_TRANSCRIPT_MESSAGES = 20


@tool(HANDOFF_TOOL)
def request_human_agent(
    reason: Reason, summary: str, open_questions: list[str] | None = None
) -> str:
    """Hand the conversation over to a human agent: the customer asks for a person; reports
    fraud, theft, a lost card or an unknown charge; wants to dispute a transaction; has a
    complaint you can't solve; accepts your offer of an agent (for something you can't do,
    explain and offer first); or two attempts to help failed. `summary`: what the customer needs
    and what you found, in their language. `open_questions`: what the agent must find out. Write
    no other text when you call it."""
    return "handed over"


def new_case_id() -> str:
    return f"NB-{secrets.token_hex(3).upper()}"


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def evidence_entry(tool_name: str, args: dict, result: str) -> dict:
    text = result if len(result) <= MAX_EVIDENCE_CHARS else result[:MAX_EVIDENCE_CHARS] + "…"
    return {"tool": tool_name, "args": args, "result": text, "at": now_iso()}


def build_case(
    *,
    session_id: str,
    lang: str,
    args: dict,
    auth: dict,
    evidence: list[dict],
    transcript: list[dict],
    verified: bool,
    intent: dict | None = None,
) -> dict:
    """The case the human agent receives. Facts and evidence come from code, not the model; the
    intent comes from the classifier (app/agent/intent.py), also in code."""
    questions = args.get("open_questions") or []
    if isinstance(questions, str):
        questions = [questions]
    return {
        "case_id": new_case_id(),
        "session_id": session_id,
        "lang": lang,
        "status": "waiting",
        "created_at": now_iso(),
        "reason": str(args.get("reason") or "other"),
        "summary": str(args.get("summary") or "").strip()[:2000],
        "open_questions": [str(q)[:300] for q in questions][:10],
        "verified_facts": {
            "identity_verified": verified,
            "customer_id": auth.get("customer_id") if verified else None,
            "first_name": auth.get("first_name") if verified else None,
            "logged_in_customer_id": auth.get("session_customer_id"),
        },
        "intent": intent,
        "evidence": evidence[-MAX_EVIDENCE:],
        "transcript": transcript[-MAX_TRANSCRIPT_MESSAGES:],
        "messages": [],  # after the handoff: customer, agent and system messages
        "agent_name": None,
    }


def case_summary(case: dict) -> dict:
    """What the agent console lists."""
    return {
        k: case.get(k)
        for k in ("case_id", "status", "created_at", "reason", "summary", "lang", "agent_name")
    } | {
        "rating": case.get("rating"),
        "customer": case.get("verified_facts", {}).get("first_name"),
        "intent": (case.get("intent") or {}).get("label"),
    }


# --- storage ------------------------------------------------------------------------------------


class AlreadyRated(Exception):
    """The case already has a satisfaction rating (one per case)."""


class RatingConflict(Exception):
    """The case kept changing while rating it and the retries ran out (retryable)."""


class CaseStore(Protocol):
    async def create(self, case: dict) -> None: ...
    async def get(self, case_id: str) -> dict | None: ...
    async def list_recent(self, limit: int = 50) -> list[dict]:
        """Newest first."""
        ...

    async def update(self, case_id: str, **fields: Any) -> dict | None: ...
    async def rate(self, case_id: str, rating: int, rated_at: str) -> dict | None:
        """Atomically store the rating of a closed case that has none. None: no such case or not
        closed. Raises AlreadyRated if it has one (also when two requests race)."""
        ...

    async def ratings(self) -> list[dict]:
        """The customers' satisfaction ratings of closed cases: [{"rating", "rated_at"}], never
        text or ids."""
        ...

    async def add_message(self, case_id: str, sender: str, text: str) -> dict | None: ...


class InMemoryCaseStore:
    def __init__(self) -> None:
        self.cases: dict[str, dict] = {}

    async def create(self, case: dict) -> None:
        self.cases[case["case_id"]] = json.loads(json.dumps(case))

    async def get(self, case_id: str) -> dict | None:
        case = self.cases.get(case_id)
        return json.loads(json.dumps(case)) if case else None

    async def list_recent(self, limit: int = 50) -> list[dict]:
        cases = sorted(self.cases.values(), key=lambda c: c["created_at"], reverse=True)
        return [json.loads(json.dumps(c)) for c in cases[:limit]]

    async def update(self, case_id: str, **fields: Any) -> dict | None:
        if case_id not in self.cases:
            return None
        self.cases[case_id].update(fields)
        return await self.get(case_id)

    async def rate(self, case_id: str, rating: int, rated_at: str) -> dict | None:
        # No await between the check and the set: atomic on the event loop.
        case = self.cases.get(case_id)
        if case is None or case.get("status") != "closed":
            return None
        if case.get("rating") is not None:
            raise AlreadyRated
        case.update(rating=rating, rated_at=rated_at)
        return json.loads(json.dumps(case))

    async def ratings(self) -> list[dict]:
        return [
            {"rating": c["rating"], "rated_at": c.get("rated_at")}
            for c in self.cases.values()
            if c.get("rating") is not None
        ]

    async def add_message(self, case_id: str, sender: str, text: str) -> dict | None:
        if case_id not in self.cases:
            return None
        self.cases[case_id]["messages"].append({"from": sender, "text": text, "at": now_iso()})
        return await self.get(case_id)


class DynamoCaseStore:
    """One item per case: case_id (PK), the case as JSON, status and created_at for listing,
    expires_at (TTL). Demo volume, so listing is a Scan."""

    def __init__(self, table: Any, ttl_days: int) -> None:
        self.table = table
        self.ttl_seconds = ttl_days * 86400

    def _put(self, case: dict, condition: dict | None = None) -> None:
        item = {
            "case_id": case["case_id"],
            "status": case["status"],
            "created_at": case["created_at"],
            "case_json": json.dumps(case, ensure_ascii=False),
            "expires_at": int(time.time()) + self.ttl_seconds,
        }
        if case.get("rating") is not None:
            # Also top-level, so the metrics can scan the numbers without reading the case text.
            item["rating"] = int(case["rating"])
            item["rated_at"] = case.get("rated_at")
        self.table.put_item(Item=item, **(condition or {}))

    def _ratings(self) -> list[dict]:
        found: list[dict] = []
        kwargs: dict[str, Any] = {
            "ProjectionExpression": "#r, rated_at",
            "FilterExpression": "attribute_exists(#r)",
            "ExpressionAttributeNames": {"#r": "rating"},
        }
        while True:
            page = self.table.scan(**kwargs)
            found.extend(
                {"rating": int(i["rating"]), "rated_at": i.get("rated_at")}
                for i in page.get("Items", [])
                if i.get("rating") is not None
            )
            if "LastEvaluatedKey" not in page:
                return found
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def _get(self, case_id: str) -> dict | None:
        item = self.table.get_item(Key={"case_id": case_id}, ConsistentRead=True).get("Item")
        return json.loads(item["case_json"]) if item else None

    def _list(self, limit: int) -> list[dict]:
        items: list[dict] = []
        kwargs: dict[str, Any] = {}
        while True:
            page = self.table.scan(**kwargs)
            items.extend(page.get("Items", []))
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        items.sort(key=lambda i: i["created_at"], reverse=True)
        return [json.loads(i["case_json"]) for i in items[:limit]]

    def _change(self, case_id: str, change) -> dict | None:
        # Read-modify-write: a handful of agents on demo volume. Good enough, not a queue.
        case = self._get(case_id)
        if case is None:
            return None
        change(case)
        self._put(case)
        return case

    def _rate(self, case_id: str, rating: int, rated_at: str) -> dict | None:
        # Still PutItem only (the role has no UpdateItem): a conditional put of the freshly read
        # case. It fails if the case got a rating, is not closed, or changed since the read (a
        # message from the advisor), in which case we read again, so nothing is overwritten.
        for _ in range(5):
            item = self.table.get_item(Key={"case_id": case_id}, ConsistentRead=True).get("Item")
            if item is None:
                return None
            case = json.loads(item["case_json"])
            if case.get("rating") is not None:
                raise AlreadyRated
            if case.get("status") != "closed":
                return None
            case.update(rating=rating, rated_at=rated_at)
            try:
                self._put(
                    case,
                    condition={
                        "ConditionExpression": (
                            "attribute_not_exists(rating) AND #s = :closed AND case_json = :seen"
                        ),
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {
                            ":closed": "closed",
                            ":seen": item["case_json"],
                        },
                    },
                )
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                    raise
                continue  # lost a race: read again and decide (rated, not closed, or retry)
            return case
        raise RatingConflict

    async def create(self, case: dict) -> None:
        await asyncio.to_thread(self._put, case)

    async def get(self, case_id: str) -> dict | None:
        return await asyncio.to_thread(self._get, case_id)

    async def list_recent(self, limit: int = 50) -> list[dict]:
        return await asyncio.to_thread(self._list, limit)

    async def update(self, case_id: str, **fields: Any) -> dict | None:
        return await asyncio.to_thread(self._change, case_id, lambda c: c.update(fields))

    async def rate(self, case_id: str, rating: int, rated_at: str) -> dict | None:
        return await asyncio.to_thread(self._rate, case_id, rating, rated_at)

    async def ratings(self) -> list[dict]:
        return await asyncio.to_thread(self._ratings)

    async def add_message(self, case_id: str, sender: str, text: str) -> dict | None:
        message = {"from": sender, "text": text, "at": now_iso()}
        return await asyncio.to_thread(
            self._change, case_id, lambda c: c["messages"].append(message)
        )


def build_case_store(settings: Any) -> CaseStore:
    if settings.cases_store == "dynamodb":
        import boto3

        table = boto3.resource("dynamodb", region_name=settings.aws_region).Table(
            settings.cases_table
        )
        return DynamoCaseStore(table, settings.case_ttl_days)
    return InMemoryCaseStore()


@lru_cache
def get_case_store() -> CaseStore:
    from app.config import get_settings

    return build_case_store(get_settings())


# --- fixed texts (not the model) -------------------------------------------------------------

TEXTS = {
    "es": {
        "handed_over": "Te comuniqué con un asesor humano. Tu caso es el **{case_id}** y le "
        "pasé el resumen de lo que conversamos, así que no tendrás que repetirlo. Escribe aquí "
        "y el asesor leerá tus mensajes.",
        "queued": "Tu mensaje quedó en el caso {case_id}. Un asesor te responderá en breve.",
        "taken": "{name} (asesor) tomó tu caso.",
        "closed": "El asesor cerró el caso {case_id}. Nova sigue disponible si necesitas algo más.",
    },
    "pt": {
        "handed_over": "Transferi você para um atendente humano. Seu caso é o **{case_id}** e "
        "passei o resumo da nossa conversa, então você não precisa repetir. Escreva aqui e o "
        "atendente lerá suas mensagens.",
        "queued": "Sua mensagem ficou no caso {case_id}. Um atendente vai responder em breve.",
        "taken": "{name} (atendente) assumiu seu caso.",
        "closed": "O atendente encerrou o caso {case_id}. A Nova continua disponível se precisar.",
    },
}


def text(lang: str, key: str, **values: Any) -> str:
    return TEXTS.get(lang, TEXTS["es"])[key].format(**values)


def satisfaction(ratings: list[dict]) -> dict:
    """Customer satisfaction with the advisor (CSAT, decision 46): count, mean, distribution 1-5
    and the window of the ratings. Numbers only."""
    values = [r["rating"] for r in ratings]
    times = sorted(r["rated_at"] for r in ratings if r.get("rated_at"))
    return {
        "rated": len(values),
        "mean": round(sum(values) / len(values), 2) if values else None,
        "distribution": {str(n): values.count(n) for n in range(1, 6)},
        "window": {"first": times[0] if times else None, "last": times[-1] if times else None},
    }


def is_open(case_state: dict | None) -> bool:
    return ((case_state or {}).get("handoff") or {}).get("status") in OPEN_STATUSES
