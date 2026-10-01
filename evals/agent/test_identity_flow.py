"""Identity verification eval runner. Run from backend/: `uv run pytest ../evals/agent`.

By default the offline model (LLM_PROVIDER=fake behaviour) decides when to ask for verification,
so this checks the flow in code. EVAL_LIVE=1 uses the configured model instead: then the
`step` after the first message measures whether the real model asks to verify when it should.
"""

import os
import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from checks import asks_for_secret, detect_lang  # noqa: E402

from app import agent  # noqa: E402
from app.agent import Notice  # noqa: E402
from app.agent.graph import build_graph  # noqa: E402
from app.sessions import get_session_store  # noqa: E402

CASES = yaml.safe_load((Path(__file__).parent / "identity.yaml").read_text(encoding="utf-8"))[
    "cases"
]
LIVE = os.environ.get("EVAL_LIVE") == "1"
SENSITIVE = re.compile(r"^[\d./ -]{6,}$")  # the customer's document, date or code


def _model():
    if LIVE:
        from app.llm import get_chat_model

        return get_chat_model()
    from app.fake_llm import OfflineChatModel

    return OfflineChatModel(delay_seconds=0)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_identity_case(case):
    get_session_store.cache_clear()
    agent._graph = build_graph(_model())
    session_id, lang, otp = f"eval-identity-{case['id']}", case["lang"], None
    try:
        for i, step in enumerate(case["steps"], 1):
            said = step["say"].replace("{otp}", otp or "")
            reply, notices = "", []
            async for piece in agent.stream_reply(session_id, said, lang):
                if isinstance(piece, Notice):
                    notices.append(piece.text)
                else:
                    reply += piece
            if notices:
                otp = re.search(r"\d{6}", notices[-1]).group()

            auth = (await get_session_store().get(session_id)).auth
            where = f"step {i} ({said!r}) -> {reply!r}"
            expected = step["step"] if isinstance(step["step"], list) else [step["step"]]
            assert auth.get("step", "none") in expected, where
            assert bool(notices) == step.get("notice", False), where
            assert detect_lang(reply) in (lang, None), where
            assert not asks_for_secret(reply), where
            if LIVE and "reply_any" in step:
                assert any(t in reply for t in step["reply_any"]), where
            if SENSITIVE.match(said):
                assert said not in reply, where
    finally:
        agent._graph = None
        get_session_store.cache_clear()
