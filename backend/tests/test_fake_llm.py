import pytest
from fastapi.testclient import TestClient

from app import agent
from app.config import Settings
from app.fake_llm import OfflineChatModel
from app.llm import ProviderNotAllowedError, ensure_allowed_provider, get_chat_model, model_id
from app.main import app
from tests.conftest import parse_sse


def test_fake_provider_is_dev_only():
    assert isinstance(
        get_chat_model(Settings(llm_provider="fake", _env_file=None)), OfflineChatModel
    )
    assert model_id(Settings(llm_provider="fake", _env_file=None)) == "fake"
    with pytest.raises(ProviderNotAllowedError):
        ensure_allowed_provider(Settings(app_env="prod", llm_provider="fake", _env_file=None))


@pytest.mark.parametrize(
    ("lang", "expected"), [("es", "Recibí tu mensaje"), ("pt", "Recebi sua mensagem")]
)
def test_fake_provider_end_to_end(interactions, lang, expected):
    agent.set_chat_model(OfflineChatModel(delay_seconds=0))
    with TestClient(app) as client:
        sid = client.post("/v1/chat/sessions", json={"lang": lang}).json()["session_id"]
        r = client.post(
            f"/v1/chat/sessions/{sid}/messages", json={"text": "hola  banco", "lang": lang}
        )
    events = parse_sse(r.text)
    assert [e for e, _ in events][-1] == "done"
    assert len(events) > 3  # streamed in pieces
    reply = "".join(d["text"] for e, d in events if e == "token")
    assert expected in reply and '"hola banco"' in reply

    (turn,) = interactions.turns.values()
    assert turn["input_tokens"] > 0 and turn["output_tokens"] > 0
