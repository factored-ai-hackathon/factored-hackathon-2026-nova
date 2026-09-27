# Chat API contract (MVP)

The frontend and the backend both code against this file. Change it first, then the code.

## Endpoints
| Endpoint | Request | Response |
|---|---|---|
| `GET /health` | – | `200 {"status":"ok","llm_provider":"huggingface"}` |
| `POST /v1/chat/sessions` | `{"lang":"es"\|"pt"}` (optional, default `es`) | `201 {"session_id":"<uuid>","lang":"es"}` |
| `POST /v1/chat/sessions/{id}/messages` | `{"text":"...","lang":"es"\|"pt"}` | `200 text/event-stream` (see below) |

Errors:
- Unknown session → `404`.
- Empty text, text over 2,000 characters, or a `lang` other than `es`/`pt` → `422`.

`lang` on a message also updates the session language.

## Stream events
Server-Sent Events, one JSON object per `data:` line:

| `event:` | `data:` | When |
|---|---|---|
| `token` | `{"text":"..."}` | Zero or more times, a piece of the reply, in order |
| `done` | `{"message_id":"<uuid>"}` | Once, last event on success |
| `error` | `{"code":"...","message":"..."}` | Once, last event on failure (e.g. `llm_error`) |

Every stream ends with exactly one `done` or one `error`.

## Python seam (API ↔ agent)
`backend/app/agent/__init__.py`:
```python
async def stream_reply(session_id: str, text: str, lang: str) -> AsyncIterator[str]
```
Yields reply text chunks. The agent keeps conversation memory per `session_id`.

## Environment variables
Names only; values go in `backend/.env` (gitignored). See `backend/.env.example`.

| Name | Used by | Notes |
|---|---|---|
| `APP_ENV` | backend | `dev` (default) or `prod`. `prod` refuses any provider but `bedrock` |
| `LLM_PROVIDER` | backend | `huggingface` (default) or `bedrock` |
| `HF_TOKEN` | backend | Personal Hugging Face token, local development only |
| `HF_MODEL_ID` | backend | Default `openai/gpt-oss-20b` |
| `HF_BASE_URL` | backend | Default `https://router.huggingface.co/v1` |
| `CORS_ORIGINS` | backend | Comma-separated, default `http://localhost:5173` |
| `VITE_API_URL` | frontend | Empty = same origin (dev proxy sends `/v1` to `localhost:8000`) |
| `VITE_MOCK` | frontend | `1` fakes the stream, no backend needed |
