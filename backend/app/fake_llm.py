"""Offline chat model for local development: LLM_PROVIDER=fake.

Streams a fixed reply in the conversation's language, with no network, token or AWS account, so
the whole app (sessions, streaming, interactions, feedback) runs anywhere. Refused in prod.
"""

import asyncio
import json
import re
from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from app.agent import identity

MAX_ECHO_CHARS = 200

REPLIES = {
    "es": (
        "**Modo sin conexión** (`LLM_PROVIDER=fake`): esta respuesta es fija, "
        "no la escribió un modelo.\n\n"
        'Recibí tu mensaje: "{echo}"\n\n'
        "Para respuestas reales:\n"
        "- **Hugging Face**: pon `HF_TOKEN` en `backend/.env`\n"
        "- **Bedrock**: `LLM_PROVIDER=bedrock` con credenciales de AWS"
    ),
    "pt": (
        "**Modo offline** (`LLM_PROVIDER=fake`): esta resposta é fixa, "
        "não foi escrita por um modelo.\n\n"
        'Recebi sua mensagem: "{echo}"\n\n'
        "Para respostas reais:\n"
        "- **Hugging Face**: coloque `HF_TOKEN` em `backend/.env`\n"
        "- **Bedrock**: `LLM_PROVIDER=bedrock` com credenciais da AWS"
    ),
}


def _lang(messages: list[BaseMessage]) -> str:
    system = next((m.text for m in messages if isinstance(m, SystemMessage)), "")
    return "pt" if system.startswith("Você") else "es"


def _reply(messages: list[BaseMessage]) -> str:
    last = messages[-1] if messages else None
    if isinstance(last, ToolMessage):  # after an account tool: show what it returned
        data = last.text[:600] + ("…" if len(last.text) > 600 else "")
        intro = TOOL_REPLIES[_lang(messages)].format(tool=last.name)
        return f"{intro}\n\n```\n{data}\n```"
    text = last.text if last else ""
    echo = " ".join(text.split())[:MAX_ECHO_CHARS]
    return REPLIES[_lang(messages)].format(echo=echo)


def _usage(messages: list[BaseMessage], reply: str) -> UsageMetadata:
    # Rough estimate (~4 characters per token) so the turn metrics have numbers.
    input_tokens = sum(len(m.text) for m in messages) // 4
    output_tokens = len(reply) // 4
    return UsageMetadata(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


VERIFY_CALL_ID = "call_offline_verify"

# Which account tool the offline model calls for a request (first match wins).
_ACCOUNT_TOOL_WORDS = (
    ("get_my_complaints", ("queja", "reclam", "caso", "pqr")),
    ("get_my_transactions", ("movim", "transac", "rechaz", "recus", "extrat", "compra")),
    ("get_my_products", ("saldo", "cuenta", "tarjeta", "conta", "cart", "producto", "limite")),
    (
        "search_policies",
        ("politica", "plazo", "prazo", "como funciona", "que significa", "horario"),
    ),
)

# Asking for a person or reporting something risky: the offline model hands over.
_HANDOFF_WORDS = ("asesor", "humano", "persona", "atendente", "fraude", "robaron", "no reconozco")
HANDOFF_TOOL = "request_human_agent"

TOOL_REPLIES = {
    "es": "**Modo sin conexión**: consulté tus datos con `{tool}` y encontré esto:",
    "pt": "**Modo offline**: consultei seus dados com `{tool}` e encontrei isto:",
}


class OfflineChatModel(BaseChatModel):
    delay_seconds: float = 0.03  # between streamed pieces, to look like a real stream
    bound_tools: tuple[str, ...] = ()

    @property
    def _llm_type(self) -> str:
        return "offline-fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "OfflineChatModel":
        # Imitates the real model: asks to verify when the customer wants their own data, and once
        # verified, calls the account tool that fits the request.
        names = tuple(getattr(t, "name", str(t)) for t in tools)
        return self.model_copy(update={"bound_tools": names})

    def _tool_call(self, messages: list[BaseMessage]) -> dict | None:
        if not messages or isinstance(messages[-1], ToolMessage):
            return None
        last = messages[-1].text
        normalized_last = identity.normalize_text(last)
        if HANDOFF_TOOL in self.bound_tools and any(w in normalized_last for w in _HANDOFF_WORDS):
            args = {"reason": "customer_request", "summary": last[:300], "open_questions": []}
            return {"name": HANDOFF_TOOL, "args": args, "id": "call_offline_handoff"}
        if identity.VERIFY_TOOL in self.bound_tools and identity.looks_like_account_request(last):
            return {"name": identity.VERIFY_TOOL, "args": {}, "id": VERIFY_CALL_ID}
        normalized = identity.normalize_text(last)
        for name, words in _ACCOUNT_TOOL_WORDS:
            if name in self.bound_tools and any(w in normalized for w in words):
                args = (
                    {"status": "declined"}
                    if name == "get_my_transactions"
                    and ("rechaz" in normalized or "recus" in normalized)
                    else {"query": last}
                    if name == "search_policies"
                    else {}
                )
                return {"name": name, "args": args, "id": f"call_offline_{name}"}
        return None

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if call := self._tool_call(messages):
            message = AIMessage("", tool_calls=[call], usage_metadata=_usage(messages, ""))
            return ChatResult(generations=[ChatGeneration(message=message)])
        reply = _reply(messages)
        message = AIMessage(reply, usage_metadata=_usage(messages, reply))
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _pieces(self, messages: list[BaseMessage]) -> Iterator[ChatGenerationChunk]:
        if call := self._tool_call(messages):
            chunk = {**call, "args": json.dumps(call["args"]), "index": 0}
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    "", tool_call_chunks=[chunk], usage_metadata=_usage(messages, "")
                )
            )
            return
        reply = _reply(messages)
        for piece in re.findall(r"\S+\s*", reply):
            yield ChatGenerationChunk(message=AIMessageChunk(piece))
        yield ChatGenerationChunk(
            message=AIMessageChunk("", usage_metadata=_usage(messages, reply))
        )

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        yield from self._pieces(messages)

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        for chunk in self._pieces(messages):
            await asyncio.sleep(self.delay_seconds)
            yield chunk
