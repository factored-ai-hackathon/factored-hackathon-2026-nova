"""Chat model factory. The provider comes from LLM_PROVIDER.

- huggingface: local development only (HF Inference Providers, OpenAI-compatible router).
  Send it only synthetic or test text.
- bedrock: production.
"""

from langchain_core.language_models import BaseChatModel

from app.config import Settings, get_settings


class ProviderNotAllowedError(RuntimeError):
    pass


def ensure_allowed_provider(settings: Settings) -> None:
    if settings.app_env == "prod" and settings.llm_provider != "bedrock":
        raise ProviderNotAllowedError(
            f"APP_ENV=prod only allows LLM_PROVIDER=bedrock (got {settings.llm_provider!r})"
        )


def get_chat_model(settings: Settings | None = None) -> BaseChatModel:
    settings = settings or get_settings()
    ensure_allowed_provider(settings)

    if settings.llm_provider == "huggingface":
        if settings.hf_token is None:
            raise RuntimeError("HF_TOKEN is not set; add it to backend/.env")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.hf_model_id,
            base_url=settings.hf_base_url,
            api_key=settings.hf_token,
            temperature=0.3,
            max_retries=1,
            timeout=60,
        )

    # TODO(bedrock): return langchain_aws.ChatBedrockConverse(model=..., region_name=...)
    # once the Bedrock model and IAM role are chosen. Add langchain-aws then.
    raise NotImplementedError("LLM_PROVIDER=bedrock is not wired up yet")
