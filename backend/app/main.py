"""FastAPI app: CORS, health check and chat routes."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "llm_provider": get_settings().llm_provider}


app.include_router(chat_router)
