"""Live metrics for the /modelos page: aggregates over the deployed traffic (decision 42).

Only aggregates leave this endpoint: counts, tokens, cost, latency percentiles and label counts,
never text, session or message ids. The result is cached in memory for CACHE_SECONDS, so however
many people have the page open, each warm Lambda reads the interactions table at most once a
minute. It never calls the model, so it is outside the chat's spend limits.

Faithfulness (decision 28) comes from the recent handed-over cases, scored with the same code as
the agent console: the share of checkable claims (amounts, dates, last digits, names) in Nova's
answers that appear in the data it consulted. Only the scores leave, never the answers.
"""

import asyncio
import time
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.agent import faithfulness
from app.agent.handoff import CaseStore, get_case_store, satisfaction
from app.agent.intent import get_intent_model
from app.api.chat import Interactions
from app.config import get_settings
from app.security_metrics import fetch_security

CACHE_SECONDS = 60
CASES_LIMIT = 50  # the agent console's queue: the most recent handed-over cases

Cases = Annotated[CaseStore, Depends(get_case_store)]

router = APIRouter(prefix="/v1/metrics", tags=["metrics"])

_cache: dict[str, Any] = {"at": None, "body": None}
_lock = asyncio.Lock()


def clear_cache() -> None:
    _cache.update(at=None, body=None)


def faithfulness_summary(cases: list[dict]) -> dict[str, Any]:
    """How faithful Nova's answers were to the data, over the cases: scores and counts only."""
    scores: list[float] = []
    supported = total = 0
    for case in cases:
        result = faithfulness.for_case(case)
        if result["overall"] is None:  # no answer with a checkable claim
            continue
        claims = [c for a in result["answers"] if a["score"] is not None for c in a["claims"]]
        scores.append(result["overall"])
        supported += sum(c["supported"] for c in claims)
        total += len(claims)
    created = sorted(c["created_at"] for c in cases if c.get("created_at"))
    return {
        "cases": len(cases),
        "scored": len(scores),
        "mean": round(sum(scores) / len(scores), 3) if scores else None,
        "claims": {
            "supported": supported,
            "total": total,
            "rate": round(supported / total, 3) if total else None,
        },
        "buckets": {
            "all": sum(s == 1 for s in scores),
            "most": sum(0.75 <= s < 1 for s in scores),
            "low": sum(s < 0.75 for s in scores),
        },
        "window": {
            "first": created[0] if created else None,
            "last": created[-1] if created else None,
        },
        "limit": CASES_LIMIT,
    }


@router.get("/live")
async def live_metrics(interactions: Interactions, cases: Cases) -> dict[str, Any]:
    async with _lock:  # concurrent viewers wait for the one scan instead of starting their own
        at = _cache["at"]
        if at is None or time.monotonic() - at >= CACHE_SECONDS:
            settings = get_settings()
            threshold = get_intent_model().threshold
            agg = await interactions.aggregate(threshold)
            body = agg.summary(
                settings.llm_price_input_per_mtok, settings.llm_price_output_per_mtok, threshold
            )
            body["faithfulness"] = faithfulness_summary(await cases.list_recent(CASES_LIMIT))
            body["satisfaction"] = satisfaction(await cases.ratings())
            body["security"] = await fetch_security(
                settings.waf_web_acl_name, settings.waf_metrics_region
            )
            body["generated_at"] = datetime.now(UTC).isoformat()
            body["cache_seconds"] = CACHE_SECONDS
            _cache.update(at=time.monotonic(), body=body)
        return _cache["body"]
