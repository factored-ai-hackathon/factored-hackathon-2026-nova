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
- Unknown or expired session (24 h without activity) → `404`.
- Empty text, text over 2,000 characters, or a `lang` other than `es`/`pt` → `422`.
- Spend limits (deployed): too many messages from one visitor in the last hour → `429 {"detail":"rate_limited"}`; the day's model budget used up → `429 {"detail":"daily_budget_exhausted"}` (until 00:00 UTC). The model is not called.
- Feedback for a `message_id` that was not recorded → `404`. `message_id` is the one from the `done` event. Rating again replaces the previous rating.

`lang` on a message also updates the session language.

## Stream events
Server-Sent Events, one JSON object per `data:` line:

| `event:` | `data:` | When |
|---|---|---|
| `token` | `{"text":"..."}` | Zero or more times, a piece of the reply, in order |
| `done` | `{"message_id":"<uuid>"}` | Once, last event on success |
| `error` | `{"code":"...","message":"..."}` | Once, last event on failure (e.g. `llm_error`) |
| `notice` | `{"kind":"otp_demo","text":"..."}` | Zero or more times: a message for the customer outside the reply. `otp_demo` is the demo SMS with the identity verification code (there is no real SMS) |

Every stream ends with exactly one `done` or one `error`.

## Identity verification
Before any personal data, the agent verifies the customer (`backend/app/agent/identity.py`, decision 22): document number → date of birth → 6-digit code (demo SMS as a `notice` event). The model can only ask to start it; the answers are handled in code, never sent to the model, and stored as placeholders in the history and the interaction log (`[identity verification input]`). 3 failures lock verification for the session; verification lasts 30 minutes. Demo customers: `docs/demo.md`.

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
Yields reply text chunks. The agent keeps conversation memory per `session_id` in the session store (`SESSIONS_STORE`), saved once the reply is complete. When `usage` is given, it is filled with the model's input/output tokens for the turn.

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
| `ORIGIN_VERIFY_SECRET` | backend | Deployed only (set by `infra/app`): requests without this `X-Origin-Verify` header get `403`. Unset locally |
| `SESSIONS_STORE` | backend | `memory` (default, local) or `dynamodb` (deployed): sessions and conversation history |
| `SESSIONS_TABLE` | backend | DynamoDB table for `dynamodb`. Default `fh26-chat-sessions` |
| `SESSION_TTL_HOURS` | backend | Hours without activity before a session expires (then `404`). Default `24` |
| `MAX_HISTORY_MESSAGES` | backend | Messages kept per conversation (user + assistant). Default `40` |
| `VERIFICATION_MAX_ATTEMPTS`, `OTP_TTL_SECONDS`, `VERIFIED_TTL_MINUTES` | backend | Identity verification. Defaults `3`, `300`, `30` |
| `DAILY_BUDGET_USD` | backend | Max model spend per day (UTC), from the tokens each turn reports. Unset = no limit. Deployed: `5` |
| `RATE_LIMIT_PER_HOUR` | backend | Max messages per visitor IP per hour. Unset = no limit. Deployed: `30` |
| `LLM_PRICE_INPUT_PER_MTOK`, `LLM_PRICE_OUTPUT_PER_MTOK` | backend | Model price in $ per million tokens, to turn tokens into dollars. Defaults `1` / `5` (Claude Haiku 4.5) |
| `INTERACTIONS_STORE` | backend | `jsonl` (default), `dynamodb` or `none` |
| `INTERACTIONS_PATH` | backend | JSONL file for `jsonl`. Default `backend/.interactions/interactions.jsonl` |
| `INTERACTIONS_TABLE` | backend | DynamoDB table for `dynamodb`. Default `fh26-chat-interactions` |
| `INTERACTIONS_TTL_DAYS` | backend | Default `30` |
| `VITE_API_URL` | frontend | Empty = same origin (dev proxy sends `/v1` to `localhost:8000`) |
| `VITE_MOCK` | frontend | `1` fakes the stream, no backend needed |
