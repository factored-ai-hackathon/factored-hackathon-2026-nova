"""Web login: document + password, then a 6-digit code sent to the customer's phone (decision 25).

There are no real accounts: every customer shares the demo password (settings.demo_password,
published in docs/demo.md), and the code is shown as a demo SMS (`demo_sms`) because no real SMS
is sent. Identity rests on the code, which is checked in code like the chat's verification.

The login creates the chat session. After the code, the session is verified and bound to the
customer, so Nova doesn't ask again (it would after `verified_ttl_minutes`, and only for this
customer). The session id is what the web app keeps; there are no other tokens.
"""

import hmac
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.agent import identity
from app.agent.identity import CustomerDirectory, IdentityVerifier, get_customer_directory
from app.config import get_settings
from app.limits import Limiter, client_ip_from, get_limiter
from app.sessions import Lang, SessionStore, get_session_store

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@lru_cache
def get_verifier() -> IdentityVerifier:
    from app.agent.graph import default_verifier

    return default_verifier()


Store = Annotated[SessionStore, Depends(get_session_store)]
Directory = Annotated[CustomerDirectory, Depends(get_customer_directory)]
Verifier = Annotated[IdentityVerifier, Depends(get_verifier)]
Limits = Annotated[Limiter, Depends(get_limiter)]


class LoginRequest(BaseModel):
    country: str = Field(max_length=40)
    document_type: str = Field(max_length=20)
    document_number: str = Field(max_length=30)
    password: str = Field(max_length=100)
    lang: Lang = "es"


class LoginResponse(BaseModel):
    login_id: str
    phone_last4: str
    code_expires_in: int  # seconds
    # Demo only: the text of the SMS that a real bank would send (there is no real SMS).
    demo_sms: str


class VerifyRequest(BaseModel):
    login_id: str = Field(max_length=64)
    code: str = Field(pattern=r"^\d{6}$")


class LoggedInCustomer(BaseModel):
    customer_id: str
    first_name: str
    country: str
    document_type: str
    document_last4: str


class VerifyResponse(BaseModel):
    session_id: str  # the chat session, already verified
    customer: LoggedInCustomer


def _same(a: str, b: str) -> bool:
    return identity.normalize_text(a) == identity.normalize_text(b)


INVALID = HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")
EXPIRED = HTTPException(status.HTTP_401_UNAUTHORIZED, "login_expired")


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    store: Store,
    directory: Directory,
    verifier: Verifier,
    limits: Limits,
) -> LoginResponse:
    client_ip = client_ip_from(request.headers, request.client.host if request.client else None)
    if refused := await limits.check(client_ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, refused)
    password_ok = hmac.compare_digest(body.password.encode(), get_settings().demo_password.encode())
    customer = await directory.find_by_document(identity.normalize_document(body.document_number))
    # One answer for every failure (wrong password, unknown document, other country or document
    # type, no mobile phone for the code), so the form can't tell who is a customer.
    if (
        not password_ok
        or customer is None
        or not _same(customer.country, body.country)
        or not _same(customer.document_type, body.document_type)
        or not customer.phone_last4
    ):
        raise INVALID
    result = verifier.start_login(customer, body.lang)
    session = await store.create(body.lang, result.auth)
    return LoginResponse(
        login_id=session.id,
        phone_last4=customer.phone_last4,
        code_expires_in=verifier.otp_ttl_seconds,
        demo_sms=result.notices[0],
    )


@router.post("/verify")
async def verify(
    body: VerifyRequest, store: Store, directory: Directory, verifier: Verifier
) -> VerifyResponse:
    session = await store.get(body.login_id)
    if session is None:
        raise EXPIRED
    outcome, auth = verifier.finish_login(session.auth, body.code)
    await store.save_messages(session.id, session.lang, session.messages, auth=auth)
    if outcome == "wrong_code":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong_code")
    if outcome != "ok":
        raise EXPIRED  # expired, too many wrong codes, or not a login: start again
    customer = await directory.find_by_id(auth["customer_id"])
    if customer is None:
        raise EXPIRED
    return VerifyResponse(
        session_id=session.id,
        customer=LoggedInCustomer(
            customer_id=customer.customer_id,
            first_name=customer.first_name,
            country=customer.country,
            document_type=customer.document_type,
            document_last4=customer.document_number[-4:],
        ),
    )
