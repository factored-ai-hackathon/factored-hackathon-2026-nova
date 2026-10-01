"""Knowledge search eval runner. Run from backend/: `uv run pytest -k knowledge_case`.

Offline (default) the model is the offline fake and the search is lexical: this only checks the
harness and that the search tool is wired in. EVAL_LIVE=1 uses the configured model and the real
search (Titan embeddings): then the facts, the citation and the "I don't know" are measured:
    EVAL_LIVE=1 LLM_PROVIDER=bedrock AWS_PROFILE=hackathon uv run pytest -k knowledge_case
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
from app.agent import knowledge  # noqa: E402
from app.agent.account_data import DemoAccountData  # noqa: E402
from app.agent.graph import build_graph  # noqa: E402
from app.agent.identity import SESSION_CUSTOMER  # noqa: E402
from app.sessions import get_session_store  # noqa: E402

CASES = yaml.safe_load((Path(__file__).parent / "knowledge.yaml").read_text(encoding="utf-8"))[
    "cases"
]
LIVE = os.environ.get("EVAL_LIVE") == "1"
LIVE_ONLY = {c["id"] for c in CASES}  # what is measured needs the real model's words


def _model():
    if LIVE:
        from app.llm import get_chat_model

        return get_chat_model()
    from app.fake_llm import OfflineChatModel

    return OfflineChatModel(delay_seconds=0)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_knowledge_case(case, monkeypatch):
    if not LIVE:  # lexical only: no network
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
    tools = [e["tool"] for e in stored.case.get("evidence", [])]
    where = f"{case['say']!r} -> {reply!r} (tools: {tools})"

    assert not asks_for_secret(reply), where
    if not LIVE:
        # The offline fake searches on policy words only; the wiring is what is checked here.
        return
    assert "search_policies" in tools, where  # answers come from the documents, not from memory
    assert detect_lang(reply) in (case["lang"], None), where
    lowered = reply.lower()
    for text in case.get("facts_all", []):
        assert text.lower() in lowered, where
    if case.get("facts_any"):
        assert any(t.lower() in lowered for t in case["facts_any"]), where
    if case.get("cites_any"):
        assert any(t.lower() in lowered for t in case["cites_any"]), f"no source named: {where}"
    for text in case.get("never_any", []):
        assert text.lower() not in lowered, where
