"""Public assistant evals. Run from backend/: `uv run pytest -k public_case`.

Offline (default) the model is a fake that says each case's `offline_reply`, so this checks the
harness and the session plumbing. With EVAL_LIVE=1 the configured provider answers, for real:
    EVAL_LIVE=1 LLM_PROVIDER=bedrock AWS_PROFILE=hackathon uv run pytest -k public_case
"""

import os
import sys
from pathlib import Path

import pytest
import yaml
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

sys.path.insert(0, str(Path(__file__).parent))
from checks import run_checks  # noqa: E402

from app.agent import public  # noqa: E402

CASES = yaml.safe_load((Path(__file__).parent / "public.yaml").read_text(encoding="utf-8"))["cases"]
LIVE = os.environ.get("EVAL_LIVE") == "1"


def _model(case):
    if LIVE:
        from app.llm import get_chat_model

        return get_chat_model()
    return GenericFakeChatModel(messages=iter([AIMessage(case["offline_reply"])]))


def content_failures(reply: str, case: dict) -> list[str]:
    failed = [f"includes:{text}" for text in case.get("includes", []) if text not in reply]
    any_of = case.get("includes_any")
    if any_of and not any(text.lower() in reply.lower() for text in any_of):
        failed.append(f"includes_any:{any_of}")
    return failed


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_public_case(case):
    public.set_public_model(_model(case))
    try:
        stream = public.stream_public_reply(f"eval-{case['id']}", case["input"], case["lang"])
        reply = "".join([piece async for piece in stream])
    finally:
        public.set_public_model(None)
    assert reply.strip(), "empty reply"
    failed = run_checks(reply, case["lang"], case["checks"]) + content_failures(reply, case)
    assert not failed, f"failed {failed}; reply: {reply!r}"


def test_the_expected_facts_are_in_the_public_knowledge():
    """The cases' expected texts come from the assistant's own knowledge, so they can't drift."""
    from app.agent import public_info

    knowledge = public_info.knowledge("es") + public_info.knowledge("pt")
    for case in CASES:
        for text in case.get("includes", []):
            assert text in knowledge, f"{case['id']}: {text!r} is not in the knowledge"
