"""Chat model factory. The provider comes from LLM_PROVIDER.

- huggingface: local development only (HF Inference Providers, OpenAI-compatible router).
  Send it only synthetic or test text.
- bedrock: production (Claude on Amazon Bedrock, Converse API). AWS credentials come from the
  standard chain: the service's IAM role in production, your AWS profile locally.
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

    from langchain_aws import ChatBedrockConverse

    return ChatBedrockConverse(
        model=settings.bedrock_model_id,
        region_name=settings.aws_region,
        temperature=0.3,
        max_tokens=settings.llm_max_tokens,
    )
