# Chat API contract (MVP)

The frontend and the backend both code against this file. Change it first, then the code.

## Endpoints
| Endpoint | Request | Response |
|---|---|---|
| `GET /health` | – | `200 {"status":"ok","llm_provider":"huggingface"}` |
| `POST /v1/chat/sessions` | `{"lang":"es"\|"pt"}` (optional, default `es`) | `201 {"session_id":"<uuid>","lang":"es"}` |
| `POST /v1/chat/sessions/{id}/messages` | `{"text":"...","lang":"es"\|"pt"}` | `200 text/event-stream` (see below) |
| `POST /v1/chat/sessions/{id}/messages/{message_id}/feedback` | `{"rating":"up"\|"down","comment":"..."}` (`comment` optional, max 500 chars) | `204` |

Errors:
- Unknown session → `404`.
- Empty text, text over 2,000 characters, or a `lang` other than `es`/`pt` → `422`.
- Feedback for a `message_id` that was not recorded → `404`. `message_id` is the one from the `done` event. Rating again replaces the previous rating.

`lang` on a message also updates the session language.

## Stream events
Server-Sent Events, one JSON object per `data:` line:

| `event:` | `data:` | When |
|---|---|---|
| `token` | `{"text":"..."}` | Zero or more times, a piece of the reply, in order |
| `done` | `{"message_id":"<uuid>"}` | Once, last event on success |
| `error` | `{"code":"...","message":"..."}` | Once, last event on failure (e.g. `llm_error`) |

Every stream ends with exactly one `done` or one `error`.

## Interactions (metrics and feedback)
Every turn is recorded before the last event (`done` or `error`) is sent: session, `message_id`, language, question and reply (card/account numbers and emails masked), model, input/output tokens, time to first token and total time, status and error code. Feedback is added to the same record. The backend also logs one JSON line per turn (`turn_metrics`) with the numbers only, no text.

Where it goes depends on `INTERACTIONS_STORE`:
- `jsonl` (default, local): appends to `backend/.interactions/interactions.jsonl` (gitignored).
- `dynamodb` (deployed): table `INTERACTIONS_TABLE`, partition key `session_id` (S), sort key `message_id` (S), TTL attribute `expires_at` (records expire after `INTERACTIONS_TTL_DAYS`).
- `none`: nothing is stored.

## Python seam (API ↔ agent)
`backend/app/agent/__init__.py`:
```python
async def stream_reply(
    session_id: str, text: str, lang: str, usage: TokenUsage | None = None
) -> AsyncIterator[str]
```
Yields reply text chunks. The agent keeps conversation memory per `session_id`. When `usage` is given, it is filled with the model's input/output tokens for the turn.

## Environment variables
Names only; values go in `backend/.env` (gitignored). See `backend/.env.example`.

| Name | Used by | Notes |
|---|---|---|
| `APP_ENV` | backend | `dev` (default) or `prod`. `prod` refuses any provider but `bedrock` |
| `LLM_PROVIDER` | backend | `huggingface` (default), `bedrock`, or `fake` (offline fixed replies, dev only) |
| `HF_TOKEN` | backend | Personal Hugging Face token, local development only |
| `HF_MODEL_ID` | backend | Default `openai/gpt-oss-20b` |
| `HF_BASE_URL` | backend | Default `https://router.huggingface.co/v1` |
| `CORS_ORIGINS` | backend | Comma-separated, default `http://localhost:5173` |
| `INTERACTIONS_STORE` | backend | `jsonl` (default), `dynamodb` or `none` |
| `INTERACTIONS_PATH` | backend | JSONL file for `jsonl`. Default `backend/.interactions/interactions.jsonl` |
| `INTERACTIONS_TABLE` | backend | DynamoDB table for `dynamodb`. Default `fh26-chat-interactions` |
| `INTERACTIONS_TTL_DAYS` | backend | Default `30` |
| `VITE_API_URL` | frontend | Empty = same origin (dev proxy sends `/v1` to `localhost:8000`) |
| `VITE_MOCK` | frontend | `1` fakes the stream, no backend needed |
