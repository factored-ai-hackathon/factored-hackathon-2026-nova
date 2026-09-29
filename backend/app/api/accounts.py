"""The logged-in customer's accounts for the web app's home page (decision 26).

Same data and rules as the agent's account tools: the customer comes from the verified chat
session the login created, never from the request. POST with the session id in the body (not a
header) so it passes CloudFront's origin request policy unchanged.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.agent import identity
from app.agent.account_data import AccountData, get_account_data
from app.api.auth import get_verifier
from app.config import get_settings
from app.sessions import SessionStore, get_session_store

router = APIRouter(prefix="/v1/accounts", tags=["accounts"])

RECENT_DAYS = 30
RECENT_LIMIT = 10


class OverviewRequest(BaseModel):
    session_id: str = Field(max_length=64)


class OverviewResponse(BaseModel):
    data_as_of: str
    products: list[dict]
    recent_transactions: list[dict]  # newest first, last RECENT_DAYS days
    open_complaints: int


@router.post("/overview")
async def overview(
    body: OverviewRequest,
    store: Annotated[SessionStore, Depends(get_session_store)],
    data: Annotated[AccountData, Depends(get_account_data)],
    verifier: Annotated[identity.IdentityVerifier, Depends(get_verifier)],
) -> OverviewResponse:
    session = await store.get(body.session_id)
    if session is None or not identity.is_verified(session.auth, verifier.now()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not_verified")
    customer_id = session.auth["customer_id"]
    as_of = get_settings().data_as_of_date
    transactions = await data.transactions(customer_id, as_of - timedelta(days=RECENT_DAYS), as_of)
    complaints = await data.complaints(customer_id)
    open_statuses = {"open", "in process", "escalated"}
    return OverviewResponse(
        data_as_of=as_of.isoformat(),
        products=await data.products(customer_id),
        recent_transactions=transactions[:RECENT_LIMIT],
        open_complaints=sum(str(c.get("status", "")).lower() in open_statuses for c in complaints),
    )
