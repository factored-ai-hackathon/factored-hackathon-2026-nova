"""Chat endpoints. See docs/api-contract.md."""

import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sse_starlette import EventSourceResponse

from app import agent
from app.sessions import Lang, SessionStore, get_session_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat", tags=["chat"])

MAX_TEXT_CHARS = 2000

ReplyStreamer = Callable[[str, str, str], AsyncIterator[str]]


def get_reply_streamer() -> ReplyStreamer:
    return agent.stream_reply


class CreateSessionRequest(BaseModel):
    lang: Lang = "es"


class SessionResponse(BaseModel):
    session_id: str
    lang: Lang


class MessageRequest(BaseModel):
    text: str = Field(max_length=MAX_TEXT_CHARS)
    # Optional: when missing, the session's language is used.
    lang: Lang | None = None

    @field_validator("text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty")
        return v


Store = Annotated[SessionStore, Depends(get_session_store)]


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(store: Store, body: CreateSessionRequest | None = None) -> SessionResponse:
    session = await store.create((body or CreateSessionRequest()).lang)
    return SessionResponse(session_id=session.id, lang=session.lang)


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str,
    body: MessageRequest,
    store: Store,
    stream_reply: Annotated[ReplyStreamer, Depends(get_reply_streamer)],
) -> EventSourceResponse:
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    if body.lang and body.lang != session.lang:
        await store.set_lang(session_id, body.lang)
    lang = body.lang or session.lang

    async def events() -> AsyncIterator[dict]:
        try:
            async for piece in stream_reply(session_id, body.text, lang):
                yield {"event": "token", "data": json.dumps({"text": piece}, ensure_ascii=False)}
        except Exception:
            logger.exception("reply failed for session %s", session_id)
            error = {"code": "llm_error", "message": "The assistant could not reply. Try again."}
            yield {"event": "error", "data": json.dumps(error)}
            return
        yield {"event": "done", "data": json.dumps({"message_id": str(uuid.uuid4())})}

    return EventSourceResponse(events())
