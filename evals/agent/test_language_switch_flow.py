"""Language switch eval runner. Run from backend/: `uv run pytest -k language_switch_case`.

Offline the fake model answers in the system prompt's language, so this checks the harness and
that the reminder reaches the model; EVAL_LIVE=1 measures whether the real model keeps up:
    EVAL_LIVE=1 LLM_PROVIDER=bedrock AWS_PROFILE=hackathon uv run pytest -k language_switch_case
"""

import os
import sys
import time
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from checks import detect_lang  # noqa: E402

from app import agent  # noqa: E402
from app.agent import knowledge  # noqa: E402
from app.agent.account_data import DemoAccountData  # noqa: E402
from app.agent.graph import build_graph  # noqa: E402
from app.agent.identity import SESSION_CUSTOMER  # noqa: E402
from app.sessions import get_session_store  # noqa: E402

CASES = yaml.safe_load(
    (Path(__file__).parent / "language_switch.yaml").read_text(encoding="utf-8")
)["cases"]
LIVE = os.environ.get("EVAL_LIVE") == "1"


def _model():
    if LIVE:
        from app.llm import get_chat_model

        return get_chat_model()
    from app.fake_llm import OfflineChatModel

    return OfflineChatModel(delay_seconds=0)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_language_switch_case(case, monkeypatch):
    if not LIVE:  # lexical search only: no network
        chunks, _ = knowledge.load_chunks()
        kb = knowledge.KnowledgeBase(chunks, knowledge.load_thresholds())
        monkeypatch.setattr(knowledge, "get_knowledge_base", lambda: kb)
    get_session_store.cache_clear()
    agent._graph = build_graph(_model(), account_data=DemoAccountData())
    auth = {
        "step": "verified",
        SESSION_CUSTOMER: "demo-001",
        "customer_id": "demo-001",
        "first_name": "Miguel",
        "verified_until": time.time() + 900,
    }
    session = await get_session_store().create(case["start"], auth)
    wrong = []
    try:
        for turn in case["turns"]:
            pieces = [p async for p in agent.stream_reply(session.id, turn["say"], turn["lang"])]
            reply = "".join(p for p in pieces if isinstance(p, str))
            if detect_lang(reply) not in (turn["lang"], None):
                wrong.append((turn["say"], reply[:160]))
    finally:
        agent._graph = None
        get_session_store.cache_clear()
    assert not wrong, f"replies in the wrong language: {wrong}"
