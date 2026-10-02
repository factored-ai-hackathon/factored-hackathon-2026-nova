"""Live metrics for the /modelos page: aggregates over the deployed traffic (decision 42).

Only aggregates leave this endpoint: counts, tokens, cost, latency percentiles and label counts,
never text, session or message ids. The result is cached in memory for CACHE_SECONDS, so however
many people have the page open, each warm Lambda reads the interactions table at most once a
minute. It never calls the model, so it is outside the chat's spend limits.
"""

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from app.agent.intent import get_intent_model
from app.api.chat import Interactions
from app.config import get_settings

CACHE_SECONDS = 60

router = APIRouter(prefix="/v1/metrics", tags=["metrics"])

_cache: dict[str, Any] = {"at": None, "body": None}
_lock = asyncio.Lock()


def clear_cache() -> None:
    _cache.update(at=None, body=None)


@router.get("/live")
async def live_metrics(interactions: Interactions) -> dict[str, Any]:
    async with _lock:  # concurrent viewers wait for the one scan instead of starting their own
        at = _cache["at"]
        if at is None or time.monotonic() - at >= CACHE_SECONDS:
            settings = get_settings()
            threshold = get_intent_model().threshold
            agg = await interactions.aggregate(threshold)
            body = agg.summary(
                settings.llm_price_input_per_mtok, settings.llm_price_output_per_mtok, threshold
            )
            body["generated_at"] = datetime.now(UTC).isoformat()
            body["cache_seconds"] = CACHE_SECONDS
            _cache.update(at=time.monotonic(), body=body)
        return _cache["body"]
