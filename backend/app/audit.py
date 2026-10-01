"""Audit trail of what the agent did with data and permissions (decision 37).

One entry per event the security story depends on: every tool call (what ran, for whom, with what
outcome), every tool call refused because the session was not verified, every argument the model
tried to pass that the tool does not take (a customer id, for example: the tools take none and the
backend uses the session's), every verification step and every handoff.

An entry never carries customer text, raw arguments or a customer id: arguments and customers are
hashes. It says that something happened and how it ended, so it can be shown to a reviewer.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

HASH_CHARS = 16


def args_hash(args: Any) -> str:
    """A stable fingerprint of the arguments (same arguments, same hash), not the arguments."""
    canonical = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:HASH_CHARS]


def customer_ref(customer_id: str | None) -> str | None:
    return hashlib.sha256(customer_id.encode()).hexdigest()[:HASH_CHARS] if customer_id else None


def entry(
    event: str,
    outcome: str,
    *,
    tool: str | None = None,
    args: Any = None,
    customer_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "event": event,  # tool_call | tool_refused | verification | handoff
        "outcome": outcome,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if tool:
        record["tool"] = tool
    if args is not None:
        record["args_hash"] = args_hash(args)
    if customer_ref(customer_id):
        record["customer"] = customer_ref(customer_id)
    if detail:
        record["detail"] = detail
    return record
