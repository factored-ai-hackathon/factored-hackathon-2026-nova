"""Human agent console API (decision 27): the cases Nova handed over, and the agent's side of the
conversation. The web page is /asesor.

Protected by one shared demo key (settings.agent_console_key, published in docs/demo.md so the
judges can play the agent). The key goes in the JSON body: CloudFront's origin request policy
doesn't forward custom headers. A real deployment would use the bank's staff identity provider.
"""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.agent import faithfulness, handoff
from app.agent.handoff import CaseStore, get_case_store
from app.config import get_settings
from app.sessions import ChatMessage, SessionStore, get_session_store

router = APIRouter(prefix="/v1/agent", tags=["agent console"])

Cases = Annotated[CaseStore, Depends(get_case_store)]
Store = Annotated[SessionStore, Depends(get_session_store)]


class KeyRequest(BaseModel):
    key: str = Field(max_length=200)


class TakeRequest(KeyRequest):
    agent_name: str = Field(min_length=1, max_length=60)


class ReplyRequest(KeyRequest):
    text: str = Field(min_length=1, max_length=2000)


def _check(key: str) -> None:
    if not hmac.compare_digest(key.encode(), get_settings().agent_console_key.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_key")


async def _case(cases: CaseStore, case_id: str) -> dict:
    case = await cases.get(case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "case_not_found")
    return case


async def _tell_customer(store: SessionStore, case: dict, text: str, status_: str | None) -> None:
    """Add the agent's message to the customer's conversation (so Nova has it as context when the
    case closes) and update the session's handoff state. status_ None: the case is closed."""
    session = await store.get(case["session_id"])
    if session is None:  # the customer's session expired: the case keeps the record
        return
    handoff_state = {"case_id": case["case_id"], "status": status_} if status_ else None
    await store.save_messages(
        session.id,
        session.lang,
        [*session.messages, ChatMessage("assistant", text)],
        auth=session.auth,
        # last_case_id: the chat still fetches the closing message after the case ends.
        case={**session.case, "handoff": handoff_state, "last_case_id": case["case_id"]},
    )


def _faithfulness(case: dict) -> dict:
    return faithfulness.for_case(case)


@router.post("/cases")
async def list_cases(body: KeyRequest, cases: Cases) -> dict:
    """The queue, newest first, with each case's overall faithfulness and the counts per status."""
    _check(body.key)
    recent = await cases.list_recent()
    summaries = [
        handoff.case_summary(c) | {"faithfulness": _faithfulness(c)["overall"]} for c in recent
    ]
    scores = [s["faithfulness"] for s in summaries if s["faithfulness"] is not None]
    stats = {status: sum(s["status"] == status for s in summaries) for status in handoff.STATUSES}
    stats["faithfulness_avg"] = round(sum(scores) / len(scores), 3) if scores else None
    return {"cases": summaries, "stats": stats}


def _shown(case: dict) -> dict:
    """The case as the console shows it. Never the customer's session id: it is the customer's
    credential for the chat, and the console key is a published demo value."""
    return {k: v for k, v in case.items() if k != "session_id"}


@router.post("/cases/{case_id}")
async def get_case(case_id: str, body: KeyRequest, cases: Cases) -> dict:
    """The case, plus how faithful Nova's answers were to the data it consulted."""
    _check(body.key)
    case = await _case(cases, case_id)
    return _shown(case) | {"faithfulness": _faithfulness(case)}


@router.post("/cases/{case_id}/take")
async def take_case(case_id: str, body: TakeRequest, cases: Cases, store: Store) -> dict:
    _check(body.key)
    case = await _case(cases, case_id)
    if case["status"] != "waiting":
        raise HTTPException(status.HTTP_409_CONFLICT, f"case_{case['status']}")
    name = body.agent_name.strip()
    case = await cases.update(case_id, status="active", agent_name=name)
    notice = handoff.text(case["lang"], "taken", name=name)
    case = await cases.add_message(case_id, "system", notice)
    await _tell_customer(store, case, notice, "active")
    return _shown(case)


@router.post("/cases/{case_id}/reply")
async def reply(case_id: str, body: ReplyRequest, cases: Cases, store: Store) -> dict:
    _check(body.key)
    case = await _case(cases, case_id)
    if case["status"] != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, f"case_{case['status']}")
    case = await cases.add_message(case_id, "agent", body.text.strip())
    await _tell_customer(store, case, f"[{case['agent_name']}] {body.text.strip()}", "active")
    return _shown(case)


@router.post("/cases/{case_id}/close")
async def close_case(case_id: str, body: KeyRequest, cases: Cases, store: Store) -> dict:
    _check(body.key)
    case = await _case(cases, case_id)
    if case["status"] == "closed":
        return _shown(case)
    notice = handoff.text(case["lang"], "closed", case_id=case_id)
    await cases.update(case_id, status="closed")
    case = await cases.add_message(case_id, "system", notice)
    await _tell_customer(store, case, notice, None)
    return _shown(case)
