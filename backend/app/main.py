"""FastAPI app: CORS, health check, login, chat and demo routes."""

import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.accounts import router as accounts_router
from app.api.agent_console import router as agent_console_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.demo import router as demo_router
from app.api.public import router as public_router
from app.config import get_settings
from app.llm import ensure_allowed_provider

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Refuse to start with a non-Bedrock provider in production.
    ensure_allowed_provider(get_settings())
    yield


app = FastAPI(title="Factored Hackathon 2026 - Contact center agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


ORIGIN_VERIFY_HEADER = "X-Origin-Verify"


@app.middleware("http")
async def require_cloudfront(request: Request, call_next):
    """Deployed, only requests that came through CloudFront (which adds the secret) get in."""
    secret = get_settings().origin_verify_secret
    if secret is not None:
        sent = request.headers.get(ORIGIN_VERIFY_HEADER, "")
        if not hmac.compare_digest(sent, secret.get_secret_value()):
            return JSONResponse({"detail": "forbidden"}, status_code=403)
    return await call_next(request)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "llm_provider": get_settings().llm_provider}


app.include_router(auth_router)
app.include_router(accounts_router)
app.include_router(agent_console_router)
app.include_router(chat_router)
app.include_router(demo_router)
app.include_router(public_router)
