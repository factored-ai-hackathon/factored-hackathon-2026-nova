"""Settings read from environment variables (and backend/.env in development)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    app_env: Literal["dev", "prod"] = "dev"
    llm_provider: Literal["huggingface", "bedrock", "fake"] = "huggingface"
    hf_token: SecretStr | None = None
    hf_model_id: str = "openai/gpt-oss-20b"
    hf_base_url: str = "https://router.huggingface.co/v1"
    # Bedrock: Claude Haiku 4.5 through the US cross-Region inference profile (the bare model ID
    # isn't supported on demand). Credentials come from the standard AWS chain (IAM role in prod).
    bedrock_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    aws_region: str = "us-east-2"
    llm_max_tokens: int = 1024
    cors_origins: str = "http://localhost:5173"
    # Deployed: CloudFront adds this secret as the X-Origin-Verify header, so the public Lambda
    # function URL rejects requests that skip CloudFront. Unset locally (no check).
    origin_verify_secret: SecretStr | None = None
    # Where each turn and its feedback are recorded (see docs/api-contract.md). Use dynamodb when
    # deployed: the jsonl file lives on local disk.
    interactions_store: Literal["jsonl", "dynamodb", "none"] = "jsonl"
    interactions_path: Path = BACKEND_DIR / ".interactions" / "interactions.jsonl"
    interactions_table: str = "fh26-chat-interactions"
    interactions_ttl_days: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
