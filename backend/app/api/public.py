"""Public assistant endpoints (outside the login): hours and branches only.

Same event stream as the account chat (docs/api-contract.md), but its own sessions and agent
(app/agent/public.py): no customer, no tools. A session created here is marked public; the
account chat refuses it, and this route refuses the account chat's sessions.
"""

import logging

from fastapi import APIRouter, HTTPException, Request, status
from sse_starlette import EventSourceResponse

from app.agent.public import is_public, public_auth, stream_public_reply
from app.api.chat import (
    CreateSessionRequest,
    Interactions,
    Limits,
    MessageRequest,
    SessionResponse,
    Store,
    turn_events,
)
from app.limits import client_ip_from

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/public/chat", tags=["public"])


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(store: Store, body: CreateSessionRequest | None = None) -> SessionResponse:
    # Only the language is taken: a public session is never bound to a customer.
    session = await store.create((body or CreateSessionRequest()).lang, public_auth())
    return SessionResponse(session_id=session.id, lang=session.lang)


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str,
    body: MessageRequest,
    request: Request,
    store: Store,
    interactions: Interactions,
    limits: Limits,
) -> EventSourceResponse:
    session = await store.get(session_id)
    if session is None or not is_public(session.auth):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    client_ip = client_ip_from(request.headers, request.client.host if request.client else None)
    if refused := await limits.check(client_ip):
        logger.warning("public turn refused: %s", refused)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, refused)
    if body.lang and body.lang != session.lang:
        await store.set_lang(session_id, body.lang)
    lang = body.lang or session.lang
    return EventSourceResponse(
        turn_events(
            session_id, body.text, lang, stream_public_reply, interactions, limits, "public"
        )
    )
