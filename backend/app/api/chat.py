"""Chat endpoints. See docs/api-contract.md."""

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sse_starlette import EventSourceResponse

from app import agent
from app.agent import TokenUsage
from app.config import get_settings
from app.interactions import InteractionStore, Rating, Turn, get_interaction_store
from app.limits import Limiter, client_ip_from, get_limiter
from app.llm import model_id
from app.sessions import Lang, SessionStore, get_session_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat", tags=["chat"])

MAX_TEXT_CHARS = 2000

MAX_COMMENT_CHARS = 500

ReplyStreamer = Callable[[str, str, str, TokenUsage], AsyncIterator[str]]


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


class FeedbackRequest(BaseModel):
    rating: Rating
    comment: str | None = Field(default=None, max_length=MAX_COMMENT_CHARS)


Store = Annotated[SessionStore, Depends(get_session_store)]
Interactions = Annotated[InteractionStore, Depends(get_interaction_store)]
Limits = Annotated[Limiter, Depends(get_limiter)]


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(store: Store, body: CreateSessionRequest | None = None) -> SessionResponse:
    session = await store.create((body or CreateSessionRequest()).lang)
    return SessionResponse(session_id=session.id, lang=session.lang)


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str,
    body: MessageRequest,
    request: Request,
    store: Store,
    interactions: Interactions,
    limits: Limits,
    stream_reply: Annotated[ReplyStreamer, Depends(get_reply_streamer)],
) -> EventSourceResponse:
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    client_ip = client_ip_from(request.headers, request.client.host if request.client else None)
    if refused := await limits.check(client_ip):
        logger.warning("turn refused: %s", refused)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, refused)
    if body.lang and body.lang != session.lang:
        await store.set_lang(session_id, body.lang)
    lang = body.lang or session.lang

    async def events() -> AsyncIterator[dict]:
        message_id = str(uuid.uuid4())
        usage = TokenUsage()
        reply: list[str] = []
        started = time.perf_counter()
        first_token_ms: int | None = None
        error_code: str | None = None
        try:
            async for piece in stream_reply(session_id, body.text, lang, usage):
                if first_token_ms is None:
                    first_token_ms = round((time.perf_counter() - started) * 1000)
                reply.append(piece)
                yield {"event": "token", "data": json.dumps({"text": piece}, ensure_ascii=False)}
        except Exception:
            logger.exception("reply failed for session %s", session_id)
            error_code = "llm_error"

        turn = Turn(
            session_id=session_id,
            message_id=message_id,
            lang=lang,
            user_text=body.text,
            reply_text="".join(reply),
            status="error" if error_code else "ok",
            error_code=error_code,
            model=model_id(get_settings()),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            first_token_ms=first_token_ms,
            total_ms=round((time.perf_counter() - started) * 1000),
        )
        await record_turn(interactions, turn)
        try:
            await limits.charge(usage.input_tokens, usage.output_tokens)
        except Exception:
            logger.exception("could not charge the daily budget for %s", message_id)

        if error_code:
            error = {"code": error_code, "message": "The assistant could not reply. Try again."}
            yield {"event": "error", "data": json.dumps(error)}
        else:
            yield {"event": "done", "data": json.dumps({"message_id": message_id})}

    return EventSourceResponse(events())


async def record_turn(interactions: InteractionStore, turn: Turn) -> None:
    """Log the turn's numbers and store it. Never breaks the chat if storing fails."""
    logger.info("turn_metrics %s", json.dumps(turn.metrics()))
    try:
        await interactions.save_turn(turn)
    except Exception:
        logger.exception("could not store turn %s", turn.message_id)


@router.post(
    "/sessions/{session_id}/messages/{message_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def post_feedback(
    session_id: str, message_id: str, body: FeedbackRequest, interactions: Interactions
) -> Response:
    if not await interactions.set_feedback(session_id, message_id, body.rating, body.comment):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
