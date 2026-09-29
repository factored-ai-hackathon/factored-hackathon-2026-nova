"""Offline chat model for local development: LLM_PROVIDER=fake.

Streams a fixed reply in the conversation's language, with no network, token or AWS account, so
the whole app (sessions, streaming, interactions, feedback) runs anywhere. Refused in prod.
"""

import asyncio
import re
from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, SystemMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

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
    last = messages[-1].text if messages else ""
    echo = " ".join(last.split())[:MAX_ECHO_CHARS]
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


class OfflineChatModel(BaseChatModel):
    delay_seconds: float = 0.03  # between streamed pieces, to look like a real stream

    @property
    def _llm_type(self) -> str:
        return "offline-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        reply = _reply(messages)
        message = AIMessage(reply, usage_metadata=_usage(messages, reply))
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _pieces(self, messages: list[BaseMessage]) -> Iterator[ChatGenerationChunk]:
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
