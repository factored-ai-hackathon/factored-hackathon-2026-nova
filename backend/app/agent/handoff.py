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
    """Hand the conversation over to a human agent. Call it when the customer asks for a person;
    reports fraud, theft, a lost card or a charge they don't recognize; wants to dispute a
    transaction; has a complaint you can't solve; accepts your offer to talk to an agent (for
    something you can't do, first explain it and offer); or after two failed attempts to help.
    `summary`: what the customer needs and what you already found, in
    the customer's language, for the agent. `open_questions`: what the agent still has to find
    out or decide. Don't write any other text when you call it."""
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
        "customer": case.get("verified_facts", {}).get("first_name"),
        "intent": (case.get("intent") or {}).get("label"),
    }


# --- storage ------------------------------------------------------------------------------------


class CaseStore(Protocol):
    async def create(self, case: dict) -> None: ...
    async def get(self, case_id: str) -> dict | None: ...
    async def list_recent(self, limit: int = 50) -> list[dict]:
        """Newest first."""
        ...

    async def update(self, case_id: str, **fields: Any) -> dict | None: ...
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

    def _put(self, case: dict) -> None:
        self.table.put_item(
            Item={
                "case_id": case["case_id"],
                "status": case["status"],
                "created_at": case["created_at"],
                "case_json": json.dumps(case, ensure_ascii=False),
                "expires_at": int(time.time()) + self.ttl_seconds,
            }
        )

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

    async def create(self, case: dict) -> None:
        await asyncio.to_thread(self._put, case)

    async def get(self, case_id: str) -> dict | None:
        return await asyncio.to_thread(self._get, case_id)

    async def list_recent(self, limit: int = 50) -> list[dict]:
        return await asyncio.to_thread(self._list, limit)

    async def update(self, case_id: str, **fields: Any) -> dict | None:
        return await asyncio.to_thread(self._change, case_id, lambda c: c.update(fields))

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


def is_open(case_state: dict | None) -> bool:
    return ((case_state or {}).get("handoff") or {}).get("status") in OPEN_STATUSES
