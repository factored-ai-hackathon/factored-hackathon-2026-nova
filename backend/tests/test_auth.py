"""Web login (document + password + code) and the demo panel. See app/api/auth.py, decision 26."""

import pytest

from app.agent.identity import (
    SESSION_CUSTOMER,
    DemoCustomerDirectory,
    DemoIndex,
    IdentityVerifier,
    get_customer_directory,
    is_verified,
)
from app.api.auth import get_verifier
from app.main import app
from app.sessions import get_session_store

CODE = "123456"
MIGUEL = {
    "country": "Colombia",
    "document_type": "CC",
    "document_number": "1.020.304.050",
    "password": "Nova2026",
}


class Clock:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock():
    clock = Clock()
    verifier = IdentityVerifier(DemoCustomerDirectory(), now=clock, new_code=lambda: CODE)
    app.dependency_overrides[get_verifier] = lambda: verifier
    yield clock
    app.dependency_overrides.pop(get_verifier, None)


def login(client, **changes):
    return client.post("/v1/auth/login", json={**MIGUEL, **changes})


def test_login_sends_a_code_and_the_code_logs_in(client, clock):
    r = login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["phone_last4"] == "0192" and body["code_expires_in"] == 300
    assert CODE in body["demo_sms"] and "0192" in body["demo_sms"]

    r = client.post("/v1/auth/verify", json={"login_id": body["login_id"], "code": CODE})
    assert r.status_code == 200
    assert r.json() == {
        "session_id": body["login_id"],
        "customer": {
            "customer_id": "demo-001",
            "first_name": "Miguel",
            "country": "Colombia",
            "document_type": "CC",
            "document_last4": "4050",
        },
    }


async def test_after_login_the_chat_session_is_verified_and_bound(client, clock):
    login_id = login(client).json()["login_id"]
    session = await get_session_store().get(login_id)
    assert not is_verified(session.auth, now=clock.t)  # not before the code
    assert CODE not in str(session.auth)  # only the salted hash is kept

    client.post("/v1/auth/verify", json={"login_id": login_id, "code": CODE})
    session = await get_session_store().get(login_id)
    assert is_verified(session.auth, now=clock.t)
    assert session.auth[SESSION_CUSTOMER] == "demo-001"
    assert session.auth["customer_id"] == "demo-001"


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "wrong"},
        {"document_number": "9999999999"},  # not a customer
        {"country": "Argentina"},  # right document, other country
        {"document_type": "CE"},  # right document, other type
    ],
)
def test_every_login_failure_gets_the_same_answer(client, clock, changes):
    r = login(client, **changes)
    assert r.status_code == 401 and r.json() == {"detail": "invalid_credentials"}


def test_country_and_document_type_ignore_case_and_accents(client, clock):
    ana = {"country": "ARGENTINA", "document_type": "dni", "document_number": "30123456"}
    assert login(client, **ana).status_code == 200


def test_customers_without_a_mobile_phone_cant_log_in(client, clock):
    from datetime import date

    from app.agent.identity import CustomerIdentity

    no_phone = CustomerIdentity("C9", "Eva", "55555555", date(1990, 1, 1), "", "Argentina", "DNI")
    app.dependency_overrides[get_customer_directory] = lambda: DemoCustomerDirectory((no_phone,))
    try:
        r = login(client, country="Argentina", document_type="DNI", document_number="55555555")
    finally:
        app.dependency_overrides.pop(get_customer_directory)
    assert r.json() == {"detail": "invalid_credentials"}


def test_three_wrong_codes_end_the_login(client, clock):
    login_id = login(client).json()["login_id"]
    verify = lambda code: client.post("/v1/auth/verify", json={"login_id": login_id, "code": code})  # noqa: E731
    assert verify("000000").json() == {"detail": "wrong_code"}
    assert verify("111111").json() == {"detail": "wrong_code"}
    assert verify("222222").json() == {"detail": "login_expired"}
    assert verify(CODE).json() == {"detail": "login_expired"}  # even the right code, now


def test_expired_code_and_unknown_login(client, clock):
    login_id = login(client).json()["login_id"]
    clock.t += 301
    r = client.post("/v1/auth/verify", json={"login_id": login_id, "code": CODE})
    assert r.status_code == 401 and r.json() == {"detail": "login_expired"}
    r = client.post("/v1/auth/verify", json={"login_id": "nope", "code": CODE})
    assert r.json() == {"detail": "login_expired"}
    assert client.post("/v1/auth/verify", json={"login_id": "x", "code": "12"}).status_code == 422


def test_a_verified_session_cant_be_logged_in_again(client, clock):
    login_id = login(client).json()["login_id"]
    client.post("/v1/auth/verify", json={"login_id": login_id, "code": CODE})
    r = client.post("/v1/auth/verify", json={"login_id": login_id, "code": CODE})
    assert r.json() == {"detail": "login_expired"}


# --- demo panel --------------------------------------------------------------------------------


def test_demo_scenarios_and_customer_lookup(client):
    r = client.get("/v1/demo/scenarios")
    assert r.status_code == 200
    body = r.json()
    assert body["password"] == "Nova2026"
    [random] = body["scenarios"]  # the local directory has no scenarios, only the pool
    assert random["key"] == "random"
    assert random["customer"]["customer_id"] in {"demo-001", "demo-002"}

    ana = client.get("/v1/demo/customers/demo-002").json()
    assert ana == {
        "customer_id": "demo-002",
        "first_name": "Ana",
        "country": "Argentina",
        "document_type": "DNI",
        "document_number": "30123456",
        "birth_date": "1985-11-02",
        "phone_last4": "4471",
    }
    assert client.get("/v1/demo/customers/nobody").status_code == 404
    assert client.get("/v1/demo/customers/a'b").status_code == 422


def test_demo_scenarios_pick_from_each_scenario(client):
    class WithScenarios(DemoCustomerDirectory):
        async def demo_index(self):
            return DemoIndex(pool=["demo-001"], scenarios={"past_due": ["demo-002"], "empty": []})

    app.dependency_overrides[get_customer_directory] = WithScenarios
    try:
        scenarios = client.get("/v1/demo/scenarios").json()["scenarios"]
    finally:
        app.dependency_overrides.pop(get_customer_directory)
    assert [(s["key"], s["customer"]["customer_id"]) for s in scenarios] == [
        ("random", "demo-001"),
        ("past_due", "demo-002"),
    ]


def test_demo_scenarios_without_customers_is_503(client):
    class Empty(DemoCustomerDirectory):
        async def demo_index(self):
            return DemoIndex()

    app.dependency_overrides[get_customer_directory] = Empty
    try:
        r = client.get("/v1/demo/scenarios")
    finally:
        app.dependency_overrides.pop(get_customer_directory)
    assert r.status_code == 503 and r.json()["detail"] == "no_demo_customers"


# --- new conversations after the login ------------------------------------------------------------


def logged_in(client) -> str:
    login_id = login(client).json()["login_id"]
    client.post("/v1/auth/verify", json={"login_id": login_id, "code": CODE})
    return login_id


async def test_a_new_conversation_keeps_the_login_verification(client, clock):
    login_id = logged_in(client)
    r = client.post(
        "/v1/chat/sessions", json={"customer_id": "demo-001", "from_session_id": login_id}
    )
    new = await get_session_store().get(r.json()["session_id"])
    source = await get_session_store().get(login_id)
    assert new.id != login_id and new.messages == []
    assert new.auth["step"] == "verified" and new.auth["customer_id"] == "demo-001"
    assert new.auth["verified_until"] == source.auth["verified_until"]  # same expiry, not renewed


@pytest.mark.parametrize(
    "setup",
    [
        "not_verified",  # the code was never entered
        "other_customer",  # the browser claims another customer
        "unknown",
    ],
)
async def test_a_new_conversation_only_inherits_a_verified_login(client, clock, setup):
    if setup == "not_verified":
        source, customer = login(client).json()["login_id"], "demo-001"
    elif setup == "other_customer":
        source, customer = logged_in(client), "demo-002"
    else:
        source, customer = "nope", "demo-001"
    r = client.post("/v1/chat/sessions", json={"customer_id": customer, "from_session_id": source})
    new = await get_session_store().get(r.json()["session_id"])
    assert new.auth == {SESSION_CUSTOMER: customer}  # bound, not verified
