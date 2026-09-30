"""The public assistant: NovaBank hours and branch locations, for visitors outside the login.

It is a separate path from the account chat (app/agent/graph.py), on purpose: a plain model call
with NO tools and no customer data, answering from a small fixed knowledge (public_info.py). What
it can't do is enforced by what it is given, not by the prompt: there is no account tool to call,
no identity verification, and no customer to read. Public sessions are marked in their auth state
and only the /v1/public routes accept them (and the account routes refuse them).
"""

from collections.abc import AsyncIterator
from functools import cache
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent import TokenUsage, public_info
from app.sessions import ChatMessage, get_session_store

PROMPTS_DIR = Path(__file__).parent / "prompts"
PUBLIC_MARK = "public"

_model: BaseChatModel | None = None


def public_auth() -> dict:
    """Initial auth state of a public session: marked, never bound to a customer."""
    return {PUBLIC_MARK: True}


def is_public(auth: dict | None) -> bool:
    return bool(auth and auth.get(PUBLIC_MARK))


@cache
def system_prompt(lang: str) -> str:
    template = (PROMPTS_DIR / f"public_{lang}.md").read_text(encoding="utf-8")
    return template.replace("{knowledge}", public_info.knowledge(lang))


def set_public_model(model: BaseChatModel | None) -> None:
    """Use a given model (tests use a fake one); None goes back to the configured one."""
    global _model
    _model = model


def _get_model() -> BaseChatModel:
    global _model
    if _model is None:
        from app.llm import get_chat_model

        _model = get_chat_model()
    return _model


async def stream_public_reply(
    session_id: str, text: str, lang: str, usage: TokenUsage | None = None
) -> AsyncIterator[str]:
    store = get_session_store()
    session = await store.get(session_id)
    history = session.messages if session else []
    messages = [
        SystemMessage(system_prompt(lang)),
        *[HumanMessage(m.content) if m.role == "user" else AIMessage(m.content) for m in history],
        HumanMessage(text),
    ]
    reply: list[str] = []
    async for chunk in _get_model().astream(messages):
        if usage is not None and chunk.usage_metadata:
            usage.add(chunk.usage_metadata)
        if piece := chunk.text:
            reply.append(piece)
            yield piece
    turn = [ChatMessage("user", text), ChatMessage("assistant", "".join(reply))]
    await store.save_messages(session_id, lang, [*history, *turn], auth=public_auth())
