"""Smoke eval runner. Run from backend/: `uv run pytest -c pyproject.toml ../evals/agent`.

By default the agent uses a fake model with fixed safe replies, so this checks the harness
and the graph without a token. Set EVAL_LIVE=1 (and HF_TOKEN) to run the cases against the
configured provider; that spends free-tier credits, so do it sparingly.
"""

import os
import sys
from pathlib import Path

import pytest
import yaml
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

sys.path.insert(0, str(Path(__file__).parent))
from checks import asks_for_secret, detect_lang, run_checks, states_amount  # noqa: E402

from app.agent.graph import build_graph  # noqa: E402

CASES = yaml.safe_load((Path(__file__).parent / "smoke.yaml").read_text(encoding="utf-8"))["cases"]
LIVE = os.environ.get("EVAL_LIVE") == "1"

FAKE_REPLIES = {
    "es": "Hola, con gusto te ayudo. Todavía no puedo consultar los datos de tu cuenta, "
    "y nunca te pediré tu PIN ni tu contraseña.",
    "pt": "Olá, posso ajudar com prazer. Ainda não consigo consultar os dados da sua conta "
    "e nunca vou pedir sua senha nem seu PIN.",
}


def _model(lang: str):
    if LIVE:
        from app.llm import get_chat_model

        return get_chat_model()
    return GenericFakeChatModel(messages=iter([AIMessage(FAKE_REPLIES[lang])]))


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_smoke_case(case):
    from app import agent

    agent._graph = build_graph(_model(case["lang"]))
    try:
        pieces = [
            p async for p in agent.stream_reply(f"eval-{case['id']}", case["input"], case["lang"])
        ]
        # A handoff adds a Notice to the stream: only the text is the reply.
        reply = "".join(p for p in pieces if isinstance(p, str))
    finally:
        agent._graph = None
    assert reply.strip(), "empty reply"
    failed = run_checks(reply, case["lang"], case["checks"])
    assert not failed, f"failed {failed}; reply: {reply!r}"


# The checks themselves must catch bad replies, or a green run means nothing.
@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("Hola, no puedo ver tu cuenta todavía, pero te ayudo con gusto.", "es"),
        ("Olá, não consigo ver sua conta ainda, mas posso ajudar.", "pt"),
    ],
)
def test_detect_lang(text, lang):
    assert detect_lang(text) == lang


@pytest.mark.parametrize(
    "text",
    [
        "Para ayudarte, indícame tu PIN.",
        "¿Cuál es tu número de tarjeta?",
        "Por favor, informe sua senha.",
        "Qual é o seu PIN?",
    ],
)
def test_asks_for_secret_catches_requests(text):
    assert asks_for_secret(text)


@pytest.mark.parametrize(
    "text",
    ["Nunca compartas tu PIN con nadie.", "Não compartilhe sua senha.", FAKE_REPLIES["es"]],
)
def test_asks_for_secret_allows_warnings(text):
    assert not asks_for_secret(text)


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        ("Tu saldo es $1.250.000", True),
        ("Seu saldo é R$ 3.200,00", True),
        ("Tienes 500 dólares disponibles", True),
        ("No puedo ver tu saldo todavía.", False),
    ],
)
def test_states_amount(text, flagged):
    assert states_amount(text) is flagged
