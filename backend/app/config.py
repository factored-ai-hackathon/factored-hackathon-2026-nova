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
    # Chat sessions and their conversation history. memory: lost on restart and not shared between
    # Lambda instances (local development); dynamodb: deployed.
    sessions_store: Literal["memory", "dynamodb"] = "memory"
    sessions_table: str = "fh26-chat-sessions"
    session_ttl_hours: int = 24
    # Messages kept per conversation (user + assistant). Bounds the item size and the input tokens.
    max_history_messages: int = 40
    # Identity verification (app/agent/identity.py). demo: fictional customers (docs/demo.md).
    # dynamodb: customers loaded from the dataset (data/scripts/load_demo_data.py).
    customer_directory: Literal["demo", "dynamodb"] = "demo"
    customers_table: str = "fh26-demo-customers"
    # Demo web login (app/api/auth.py): one password for every customer, published in docs/demo.md
    # (the dataset is synthetic; the code sent to the phone is what proves identity).
    demo_password: str = "Nova2026"
    verification_max_attempts: int = 3
    otp_ttl_seconds: int = 300
    verified_ttl_minutes: int = 30
    # Spend limits (see docs/api-contract.md). Unset = no limit (local development).
    daily_budget_usd: float | None = None
    rate_limit_per_hour: int | None = None
    # Price of the model, to turn tokens into dollars. Defaults: Claude Haiku 4.5 on Bedrock.
    llm_price_input_per_mtok: float = 1.0
    llm_price_output_per_mtok: float = 5.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
