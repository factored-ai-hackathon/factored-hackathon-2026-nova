import os

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings, get_settings
from app.llm import ProviderNotAllowedError, ensure_allowed_provider, get_chat_model


def test_prod_refuses_non_bedrock():
    with pytest.raises(ProviderNotAllowedError):
        ensure_allowed_provider(Settings(app_env="prod", llm_provider="huggingface"))
    ensure_allowed_provider(Settings(app_env="prod", llm_provider="bedrock"))
    ensure_allowed_provider(Settings(app_env="dev", llm_provider="huggingface"))


def test_app_refuses_to_start_in_prod_with_huggingface(monkeypatch):
    from app.main import app

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("LLM_PROVIDER", "huggingface")
    get_settings.cache_clear()
    try:
        with pytest.raises(ProviderNotAllowedError), TestClient(app):
            pass
    finally:
        get_settings.cache_clear()


def test_huggingface_model_config():
    settings = Settings(
        llm_provider="huggingface",
        hf_token=SecretStr("test-token"),
        hf_model_id="some/model",
        _env_file=None,
    )
    model = get_chat_model(settings)
    assert model.model_name == "some/model"
    assert str(model.openai_api_base) == "https://router.huggingface.co/v1"


def test_huggingface_requires_token():
    with pytest.raises(RuntimeError, match="HF_TOKEN"):
        get_chat_model(Settings(llm_provider="huggingface", hf_token=None, _env_file=None))


@pytest.fixture
def no_local_aws(monkeypatch):
    """Keep unit tests away from local AWS config and credentials (the client needs none)."""
    monkeypatch.setenv("AWS_CONFIG_FILE", os.devnull)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", os.devnull)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


def test_bedrock_model_config(no_local_aws):
    settings = Settings(
        llm_provider="bedrock",
        bedrock_model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        aws_region="us-east-2",
        _env_file=None,
    )
    model = get_chat_model(settings)
    assert model.model_id == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert model.region_name == "us-east-2"


def test_prod_with_bedrock_builds_a_model(no_local_aws):
    model = get_chat_model(Settings(app_env="prod", llm_provider="bedrock", _env_file=None))
    assert model.model_id.startswith("us.anthropic.claude-haiku-4-5")


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("HF_TOKEN"), reason="set HF_TOKEN to run live tests")
async def test_live_huggingface_reply():
    """Sends one synthetic greeting to the HF router. Costs a tiny amount of free credits."""
    model = get_chat_model(Settings(llm_provider="huggingface"))
    reply = await model.ainvoke("Responde solo con la palabra: hola")
    assert reply.text.strip()


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("BEDROCK_LIVE"), reason="set BEDROCK_LIVE=1 to call Bedrock")
async def test_live_bedrock_reply():
    """Sends one synthetic greeting to Bedrock. Needs AWS credentials and model access."""
    model = get_chat_model(Settings(llm_provider="bedrock"))
    reply = await model.ainvoke("Responde solo con la palabra: hola")
    assert reply.text.strip()
