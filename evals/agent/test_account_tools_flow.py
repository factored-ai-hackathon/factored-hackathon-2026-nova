"""Account tools eval runner. Run from backend/: `uv run pytest ../evals/agent`.

Offline (default) the model is the offline fake, so this checks the security in code: data is
only read for the session's customer, never before verification. EVAL_LIVE=1 uses the configured
model: then `tool`, `amount` and `live_contains_any` measure whether it picks the right tool and
answers from its data.
"""

import os
import re
import sys
import time
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from checks import asks_for_secret, detect_lang  # noqa: E402

from app import agent  # noqa: E402
from app.agent.account_data import DemoAccountData  # noqa: E402
from app.agent.graph import build_graph  # noqa: E402
from app.agent.identity import DEMO_CUSTOMERS, SESSION_CUSTOMER  # noqa: E402
from app.sessions import get_session_store  # noqa: E402

CASES = yaml.safe_load((Path(__file__).parent / "account_tools.yaml").read_text(encoding="utf-8"))[
    "cases"
]
LIVE = os.environ.get("EVAL_LIVE") == "1"
NAMES = {c.customer_id: c.first_name for c in DEMO_CUSTOMERS}


class SpyData(DemoAccountData):
    def __init__(self):
        super().__init__()
        self.reads: list[tuple[str, str]] = []

    async def products(self, customer_id):
        self.reads.append(("get_my_products", customer_id))
        return await super().products(customer_id)

    async def transactions(self, customer_id, since, until):
        self.reads.append(("get_my_transactions", customer_id))
        return await super().transactions(customer_id, since, until)

    async def complaints(self, customer_id):
        self.reads.append(("get_my_complaints", customer_id))
        return await super().complaints(customer_id)


def _model():
    if LIVE:
        from app.llm import get_chat_model

        return get_chat_model()
    from app.fake_llm import OfflineChatModel

    return OfflineChatModel(delay_seconds=0)


def _auth(case) -> dict:
    customer = case["customer"]
    if case.get("verified", True) is False:
        return {SESSION_CUSTOMER: customer}
    return {
        "step": "verified",
        SESSION_CUSTOMER: customer,
        "customer_id": customer,
        "first_name": NAMES[customer],
        "verified_until": time.time() + 600,
    }


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_account_tools_case(case):
    get_session_store.cache_clear()
    spy = SpyData()
    agent._graph = build_graph(_model(), account_data=spy)
    store = get_session_store()
    session = await store.create(case["lang"], _auth(case))
    try:
        pieces = [p async for p in agent.stream_reply(session.id, case["say"], case["lang"])]
        reply = "".join(p for p in pieces if isinstance(p, str))
        auth = (await store.get(session.id)).auth
    finally:
        agent._graph = None
        get_session_store.cache_clear()

    where = f"{case['say']!r} -> {reply!r} (reads: {spy.reads})"
    # Security, always: only the session's customer, and nothing before verification.
    assert all(customer == case["customer"] for _, customer in spy.reads), where
    if case.get("verified", True) is False:
        assert spy.reads == [], where
    assert not asks_for_secret(reply), where
    for text in case.get("never", []):
        assert text not in reply, where
    if "step" in case:
        assert auth.get("step", "none") == case["step"], where

    # What the model should do (offline: the fake's keyword routing; live: the real model).
    if "tool" in case:
        tools = {tool for tool, _ in spy.reads}
        assert (case["tool"] in tools) if case["tool"] else not tools, where
    if "contains_any" in case:
        assert any(t.lower() in reply.lower() for t in case["contains_any"]), where
    if "amount" in case:
        assert str(case["amount"]) in re.sub(r"[.,\s]", "", reply), where
    if LIVE:
        assert detect_lang(reply) in (case["lang"], None), where
        if "live_contains_any" in case:
            assert any(t.lower() in reply.lower() for t in case["live_contains_any"]), where
