"""Handoff and hard-case eval runner.
Run from backend/: `uv run pytest -c pyproject.toml ../evals/agent`.

Offline the fake model hands over on keywords, so this checks the handoff in code: a case with
code-built facts, and the bot out of the conversation. EVAL_LIVE=1 measures the real model:
does it hand over when it should, and ask or explain (without handing over) when it shouldn't.
"""

import os
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
from app.agent.handoff import InMemoryCaseStore  # noqa: E402
from app.agent.identity import SESSION_CUSTOMER  # noqa: E402
from app.sessions import get_session_store  # noqa: E402

CASES = yaml.safe_load((Path(__file__).parent / "handoff.yaml").read_text(encoding="utf-8"))[
    "cases"
]
LIVE = os.environ.get("EVAL_LIVE") == "1"
# Offline, the fake model only hands over on keywords: these cases need the real model.
LIVE_ONLY = {"es-fraud", "pt-stolen-card"}


def _model():
    if LIVE:
        from app.llm import get_chat_model

        return get_chat_model()
    from app.fake_llm import OfflineChatModel

    return OfflineChatModel(delay_seconds=0)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_handoff_case(case):
    if not LIVE and case["id"] in LIVE_ONLY:
        pytest.skip("needs the real model (EVAL_LIVE=1)")
    get_session_store.cache_clear()
    cases = InMemoryCaseStore()
    agent._graph = build_graph(_model(), account_data=DemoAccountData(), case_store=cases)
    auth = {
        "step": "verified",
        SESSION_CUSTOMER: "demo-001",
        "customer_id": "demo-001",
        "first_name": "Miguel",
        "verified_until": time.time() + 600,
    }
    session = await get_session_store().create(case["lang"], auth)
    try:
        pieces = [p async for p in agent.stream_reply(session.id, case["say"], case["lang"])]
        stored = await get_session_store().get(session.id)
    finally:
        agent._graph = None
        get_session_store.cache_clear()
    reply = "".join(p for p in pieces if isinstance(p, str))
    opened = await cases.list_recent()

    where = f"{case['say']!r} -> {reply!r} (cases: {opened})"
    assert not asks_for_secret(reply), where
    if "intent" in case:
        assert (stored.case.get("intent") or {}).get("label") == case["intent"], where
    if case["handoff"] != "optional":
        assert bool(opened) == case["handoff"], where
    if opened:
        [c] = opened
        assert c["verified_facts"]["customer_id"] == "demo-001", where  # from the session
        assert c["summary"], where
        if LIVE and "reason_any" in case:
            assert c["reason"] in case["reason_any"], where
        if LIVE and "handoff_reply_has" in case:
            assert all(t in reply for t in case["handoff_reply_has"]), where
    if LIVE:
        assert detect_lang(reply) in (case["lang"], None), where
        if not opened and "live_reply_any" in case:
            assert any(t.lower() in reply.lower() for t in case["live_reply_any"]), where
        for claim in case.get("never_claims", []):
            assert claim.lower() not in reply.lower(), where
