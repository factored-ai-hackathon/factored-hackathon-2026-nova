"""The public assistant (outside the login): hours and branches only, no customer data."""

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.agent import public, public_info
from app.config import Settings
from app.limits import Limiter, MemoryCounterStore, get_limiter
from app.main import app
from app.sessions import get_session_store
from tests.conftest import parse_sse


class RecordingModel(GenericFakeChatModel):
    """Fake model that keeps what it was sent."""

    sent: list = []

    def bind_tools(self, *args, **kwargs):
        raise AssertionError("the public assistant must not have tools")

    def _stream(self, messages, *args, **kwargs):
        self.sent.append(messages)
        yield from super()._stream(messages, *args, **kwargs)


def model(*replies: str) -> RecordingModel:
    return RecordingModel(messages=iter([AIMessage(r) for r in replies]), sent=[])


@pytest.fixture
def public_client():
    def _make(*replies: str) -> tuple[TestClient, RecordingModel]:
        fake = model(*replies)
        public.set_public_model(fake)
        return TestClient(app), fake

    yield _make
    public.set_public_model(None)


def new_session(client: TestClient, lang: str = "es") -> str:
    res = client.post("/v1/public/chat/sessions", json={"lang": lang})
    assert res.status_code == 201
    return res.json()["session_id"]


def say(client: TestClient, session_id: str, text: str, path: str = "/v1/public/chat"):
    return client.post(f"{path}/sessions/{session_id}/messages", json={"text": text})


# --- knowledge -----------------------------------------------------------------------


def test_every_country_has_branches_and_a_whatsapp_number():
    assert set(public_info.PUBLIC_INFO) == set(public_info.COUNTRIES)
    for info in public_info.PUBLIC_INFO.values():
        assert len(info.branches) >= 3
        assert info.whatsapp.startswith("+")


@pytest.mark.parametrize("lang", ["es", "pt"])
def test_prompt_carries_the_whole_knowledge_in_the_right_language(lang):
    prompt = public.system_prompt(lang)
    for info in public_info.PUBLIC_INFO.values():
        assert info.whatsapp in prompt
        for branch in info.branches:
            assert branch.address in prompt
            assert branch.city in prompt
    assert "{knowledge}" not in prompt
    assert ("Você" in prompt) == (lang == "pt")
    assert ("segunda-feira" in prompt) == (lang == "pt")


def test_hours_are_formatted_per_language():
    hours = ((0, 4, "09:00", "16:00"), (5, 5, "09:00", "13:00"))
    assert public_info.format_hours(hours, "es") == (
        "lunes a viernes 09:00-16:00; sábado 09:00-13:00; domingos y feriados: cerrado"
    )
    assert public_info.format_hours(hours, "pt").startswith(
        "segunda-feira a sexta-feira 09:00-16:00"
    )


# --- chat ------------------------------------------------------------------------------


def test_public_chat_streams_a_reply(public_client):
    client, _ = public_client("Abrimos de lunes a viernes.")
    session_id = new_session(client)
    res = say(client, session_id, "¿A qué hora abren?")
    assert res.status_code == 200
    events = parse_sse(res.text)
    assert "".join(d["text"] for e, d in events if e == "token") == "Abrimos de lunes a viernes."
    assert events[-1][0] == "done"


def test_the_model_gets_only_the_public_prompt_and_no_tools(public_client):
    client, fake = public_client("Hola")
    say(client, new_session(client, "pt"), "Que horas vocês abrem?")
    (messages,) = fake.sent
    assert messages[0].text == public.system_prompt("pt")
    assert messages[-1].text == "Que horas vocês abrem?"
    # bind_tools raises in RecordingModel: no tool exists that could read customer data.


def test_public_session_has_no_customer_and_is_marked(public_client):
    client, _ = public_client()
    session_id = new_session(client)
    session = get_session_store()._sessions[session_id]  # in-memory store in tests
    assert session.auth == {public.PUBLIC_MARK: True}


def test_history_is_kept_between_turns(public_client):
    client, fake = public_client("Primera", "Segunda")
    session_id = new_session(client)
    say(client, session_id, "uno")
    say(client, session_id, "dos")
    second = fake.sent[1]
    assert [m.text for m in second[1:]] == ["uno", "Primera", "dos"]


def test_turns_are_recorded_in_the_public_channel(public_client, interactions):
    client, _ = public_client("Hola")
    say(client, new_session(client), "hola")
    (turn,) = interactions.turns.values()
    assert turn["channel"] == "public"


def test_public_and_account_sessions_do_not_mix(public_client, client):
    public_client("Hola")
    public_id = new_session(client)
    account_id = client.post("/v1/chat/sessions").json()["session_id"]
    # A public session can't be used in the account chat (it would reach the account agent)...
    assert say(client, public_id, "hola", "/v1/chat").status_code == 404
    # ...and an account session can't be used in the public one.
    assert say(client, account_id, "hola").status_code == 404


def test_unknown_session(public_client):
    client, _ = public_client()
    assert say(client, "nope", "hola").status_code == 404


def test_public_chat_is_rate_limited(public_client):
    client, _ = public_client("Hola", "Hola")
    lim = Limiter(Settings(_env_file=None, rate_limit_per_hour=1), MemoryCounterStore())
    app.dependency_overrides[get_limiter] = lambda: lim
    try:
        session_id = new_session(client)
        assert say(client, session_id, "uno").status_code == 200
        assert say(client, session_id, "dos").status_code == 429
    finally:
        app.dependency_overrides.pop(get_limiter, None)
