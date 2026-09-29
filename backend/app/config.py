"""Settings read from environment variables (and backend/.env in development)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    app_env: Literal["dev", "prod"] = "dev"
    llm_provider: Literal["huggingface", "bedrock"] = "huggingface"
    hf_token: SecretStr | None = None
    hf_model_id: str = "openai/gpt-oss-20b"
    hf_base_url: str = "https://router.huggingface.co/v1"
    # Bedrock: Claude Haiku 4.5 through the US cross-Region inference profile (the bare model ID
    # isn't supported on demand). Credentials come from the standard AWS chain (IAM role in prod).
    bedrock_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    aws_region: str = "us-east-2"
    llm_max_tokens: int = 1024
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
