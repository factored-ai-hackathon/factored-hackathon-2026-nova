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
from app.agent import Notice, TokenUsage
from app.agent.handoff import CaseStore, get_case_store
from app.agent.identity import (
    SESSION_CUSTOMER,
    CustomerDirectory,
    IdentityVerifier,
    get_customer_directory,
    is_verified,
    session_auth,
)
from app.agent.public import is_public
from app.api.auth import get_verifier
from app.api.demo import CUSTOMER_ID_PATTERN
from app.config import get_settings
from app.interactions import InteractionStore, Rating, Turn, get_interaction_store
from app.limits import Limiter, client_ip_from, get_limiter
from app.llm import model_id
from app.sessions import Lang, SessionStore, get_session_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat", tags=["chat"])

MAX_TEXT_CHARS = 2000

MAX_COMMENT_CHARS = 500

ReplyStreamer = Callable[[str, str, str, TokenUsage], AsyncIterator[str | Notice]]


def get_reply_streamer() -> ReplyStreamer:
    return agent.stream_reply


class CreateSessionRequest(BaseModel):
    lang: Lang = "es"
    # The customer logged in to the demo web session (POST /v1/demo/login). Only that customer can
    # then be verified in the chat. It grants nothing by itself: verification is still required.
    customer_id: str | None = Field(default=None, pattern=CUSTOMER_ID_PATTERN)
    # A new conversation for someone already logged in: the session the login created. While that
    # session is verified, the new one is too (same customer, same expiry); else it's just bound.
    from_session_id: str | None = Field(default=None, max_length=64)


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
Directory = Annotated[CustomerDirectory, Depends(get_customer_directory)]


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    store: Store,
    directory: Directory,
    verifier: Annotated[IdentityVerifier, Depends(get_verifier)],
    body: CreateSessionRequest | None = None,
) -> SessionResponse:
    body = body or CreateSessionRequest()
    if body.customer_id is not None and await directory.find_by_id(body.customer_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "customer_not_found")
    auth = session_auth(body.customer_id)
    if body.from_session_id and (source := await store.get(body.from_session_id)):
        same_customer = body.customer_id in (None, source.auth.get(SESSION_CUSTOMER))
        if same_customer and is_verified(source.auth, verifier.now()):
            auth = {k: v for k, v in source.auth.items() if k != "failures"}
    session = await store.create(body.lang, auth)
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
    if session is None or is_public(session.auth):  # public sessions belong to /v1/public
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    client_ip = client_ip_from(request.headers, request.client.host if request.client else None)
    if refused := await limits.check(client_ip):
        logger.warning("turn refused: %s", refused)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, refused)
    if body.lang and body.lang != session.lang:
        await store.set_lang(session_id, body.lang)
    lang = body.lang or session.lang

    return EventSourceResponse(
        turn_events(session_id, body.text, lang, stream_reply, interactions, limits)
    )


async def turn_events(
    session_id: str,
    text: str,
    lang: str,
    stream_reply: ReplyStreamer,
    interactions: InteractionStore,
    limits: Limiter,
    channel: str = "account",
) -> AsyncIterator[dict]:
    """One turn as server-sent events (token, notice, done or error); records it and charges the
    budget. Shared by the account chat and the public assistant."""
    message_id = str(uuid.uuid4())
    usage = TokenUsage()
    reply: list[str] = []
    started = time.perf_counter()
    first_token_ms: int | None = None
    error_code: str | None = None
    try:
        async for piece in stream_reply(session_id, text, lang, usage):
            if isinstance(piece, Notice):
                notice = {"kind": piece.kind, "text": piece.text}
                yield {"event": "notice", "data": json.dumps(notice, ensure_ascii=False)}
                continue
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
        # Verification answers (document, date of birth, code) are never logged.
        user_text="[identity verification input]" if usage.sensitive_input else text,
        reply_text="".join(reply),
        status="error" if error_code else "ok",
        error_code=error_code,
        model=model_id(get_settings()),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        first_token_ms=first_token_ms,
        total_ms=round((time.perf_counter() - started) * 1000),
        channel=channel,
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


async def record_turn(interactions: InteractionStore, turn: Turn) -> None:
    """Log the turn's numbers and store it. Never breaks the chat if storing fails."""
    logger.info("turn_metrics %s", json.dumps(turn.metrics()))
    try:
        await interactions.save_turn(turn)
    except Exception:
        logger.exception("could not store turn %s", turn.message_id)


class HandoffUpdatesRequest(BaseModel):
    after: int = Field(default=0, ge=0)  # how many case messages the client already has


@router.post("/sessions/{session_id}/handoff")
async def handoff_updates(
    session_id: str,
    body: HandoffUpdatesRequest,
    store: Store,
    cases: Annotated[CaseStore, Depends(get_case_store)],
) -> dict:
    """While a human agent has the conversation, the chat polls this for the agent's messages.
    The session id is the credential: only its own case is returned."""
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    state = (session.case or {}).get("handoff") or {}
    case_id = state.get("case_id") or (session.case or {}).get("last_case_id")
    case = await cases.get(case_id) if case_id else None
    if case is None or case["session_id"] != session_id:
        return {"status": "none", "case_id": None, "agent_name": None, "messages": [], "next": 0}
    new = [
        {"from": m["from"], "text": m["text"], "at": m["at"]}
        for m in case["messages"][body.after :]
        if m["from"] in ("agent", "system")
    ]
    return {
        "status": case["status"],
        "case_id": case["case_id"],
        "agent_name": case.get("agent_name"),
        "messages": new,
        "next": len(case["messages"]),
    }


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
