# Chat API contract (MVP)

The frontend and the backend both code against this file. Change it first, then the code.

## Endpoints
| Endpoint | Request | Response |
|---|---|---|
| `GET /health` | – | `200 {"status":"ok","llm_provider":"huggingface"}` |
| `POST /v1/auth/login` | `{"country","document_type","document_number","password","lang"}` | `200 {"login_id","phone_last4","code_expires_in":300,"demo_sms":"..."}` |
| `POST /v1/auth/verify` | `{"login_id","code":"123456"}` | `200 {"session_id","customer":{"customer_id","first_name","country","document_type","document_last4"}}` |
| `GET /v1/demo/scenarios` | – | `200 {"password","scenarios":[{"key","customer":{"customer_id","first_name","country","document_type","document_number","birth_date","phone_last4"}}]}` |
| `GET /v1/demo/customers/{customer_id}` | – | `200 {"customer_id",...}` (same fields as a scenario's customer) |
| `POST /v1/accounts/overview` | `{"session_id"}` (a verified chat session, from the login) | `200 {"data_as_of","products":[...],"recent_transactions":[...],"open_complaints":0}` |
| `POST /v1/chat/sessions/{id}/handoff` | `{"after":0}` | `200 {"status":"none"\|"waiting"\|"active"\|"closed","case_id","agent_name","messages":[{"from":"agent"\|"system","text","at"}],"rating","next"}` (`rating`: the customer's 1-5 rating of the closed case, or `null`) |
| `POST /v1/chat/sessions/{id}/handoff/rating` | `{"rating":1-5}` | `200 {"case_id","rating"}`: the customer's satisfaction with the human agent (decision 46) |
| `POST /v1/agent/cases` | `{"key"}` | `200 {"cases":[{case_id,status,created_at,reason,summary,lang,agent_name,customer,faithfulness}],"stats":{"waiting","active","closed","faithfulness_avg","satisfaction_avg","rated"}}`; each case also has `rating` (1-5 or `null`) |
| `POST /v1/agent/cases/{case_id}` | `{"key"}` | `200` the case (summary, open questions, verified facts, evidence, transcript, messages) plus `faithfulness` (see below) |
| `POST /v1/agent/cases/{case_id}/take` | `{"key","agent_name"}` | `200` the case, now `active` (`409` if not `waiting`) |
| `POST /v1/agent/cases/{case_id}/reply` | `{"key","text"}` | `200` the case (`409` if not `active`) |
| `POST /v1/agent/cases/{case_id}/close` | `{"key"}` | `200` the case, `closed` |
| `POST /v1/chat/sessions` | `{"lang":"es"\|"pt","customer_id":"...","from_session_id":"..."}` (all optional; default `es`) | `201 {"session_id":"<uuid>","lang":"es"}` |
| `POST /v1/chat/sessions/{id}/messages` | `{"text":"...","lang":"es"\|"pt"}` | `200 text/event-stream` (see below) |
| `POST /v1/public/chat/sessions` | `{"lang":"es"\|"pt"}` (optional) | `201 {"session_id","lang"}`: a public session (no customer) |
| `POST /v1/public/chat/sessions/{id}/messages` | `{"text","lang"}` | `200 text/event-stream`, same events as the account chat |
| `POST /v1/chat/sessions/{id}/messages/{message_id}/feedback` | `{"rating":"up"\|"down","comment":"..."}` (`comment` optional, max 500 chars) | `204` |
| `GET /v1/metrics/live` | – | `200` aggregates over the recorded turns (see "Live metrics" below) |

Errors:
- Login: any wrong data (password, document, country, document type, or a customer without a mobile phone) → `401 {"detail":"invalid_credentials"}`, the same for all. Verify: wrong code → `401 {"detail":"wrong_code"}`; expired code, 3 wrong codes, or an unknown `login_id` → `401 {"detail":"login_expired"}` (log in again). Login attempts count toward the per-visitor rate limit (`429`).
- Accounts overview: a session that doesn't exist or isn't verified (or whose verification expired) → `401 {"detail":"not_verified"}`.
- Demo: a `customer_id` that isn't in the directory → `404 {"detail":"customer_not_found"}` (also for a new session with that `customer_id`); characters other than letters, digits, `-`, `_` (or over 64) → `422`. No customers loaded → `503 {"detail":"no_demo_customers"}`.
- Unknown or expired session (24 h without activity) → `404`.
- Empty text, text over 2,000 characters, or a `lang` other than `es`/`pt` → `422`.
- Spend limits (deployed): too many messages from one visitor in the last hour → `429 {"detail":"rate_limited"}`; the day's model budget used up → `429 {"detail":"daily_budget_exhausted"}` (until 00:00 UTC). The model is not called.
- Handoff rating: a session with no case, a case that is not `closed`, or a case that is not the session's → `404 {"detail":"case_not_found"}` (unknown session: `404`); a case already rated → `409 {"detail":"already_rated"}`; `rating` that is not an integer from 1 to 5 → `422`.
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

## Web login (decision 25)
1. `POST /v1/auth/login` checks the document (letters and digits only, uppercase, so `1.020.304.050` works), its country and type, and the password. Every customer shares the demo password (`DEMO_PASSWORD`, published in `docs/demo.md`: the dataset is synthetic). It creates the **chat session** and sends a 6-digit code to the phone: there is no real SMS, so its text comes back as `demo_sms`.
2. `POST /v1/auth/verify` with the code (3 tries, 5 minutes). The chat session (`session_id` = `login_id`) is now **verified** for this customer: Nova answers without asking again. Verification lasts `VERIFIED_TTL_MINUTES`; after that Nova verifies again in the chat (document, date of birth, code), and only as this customer.

The session id is the only credential the web app keeps. A new conversation for the same customer: `POST /v1/chat/sessions` with `customer_id` and `from_session_id` (the login's session); while that session is verified, the new one is too, with the same expiry. Otherwise the new session is only **bound** to `customer_id`: verification in the chat only succeeds as that customer (someone else's correct data fails like wrong data). Binding only restricts, so it grants nothing by itself.

## Demo panel
`GET /v1/demo/scenarios` returns the demo password and one customer per scenario (`random`, `declined_transaction`, `open_complaint`, `past_due`; see `data/scripts/load_demo_data.py`), picked again on every call. `GET /v1/demo/customers/{id}` returns any customer of the dataset. They show what the customer would know (document, date of birth); logging in still needs the code.

## Public assistant (decision 30)
For visitors outside the login. `POST /v1/public/chat/sessions` creates a session marked `public`; `POST /v1/public/chat/sessions/{id}/messages` streams the reply like the account chat (`token`, `done`, `error`; never `notice`). The agent (`backend/app/agent/public.py`) is a plain model call with a system prompt holding the fictitious branches, hours and WhatsApp numbers (`public_info.py`): no tools, no identity verification, no customer data. It answers only hours and branch locations (ES/PT) and sends people without an account to the WhatsApp number of their country. Sessions are not interchangeable: a public session id on `/v1/chat/...`, or an account session id on `/v1/public/chat/...`, answers `404`. Same spend limits and errors as the account chat; interactions are stored with `channel: "public"`.

## Knowledge search (decision 32)
The model can call `search_policies(query)` at any time, verified or not (`backend/app/agent/knowledge.py`): it searches 42 team-written, fictitious documents (ES + PT) in the conversation's language and returns up to 3 `{title, text, source}`, or an empty list with a note to not answer from memory. The consulted documents are added to the case's evidence (`tool: "search_policies"`), so the console's faithfulness view checks the answer against them. Retrieval: BM25 + Titan embeddings (needs `bedrock:InvokeModel` on `amazon.titan-embed-text-v2:0`; without it, lexical only); `KNOWLEDGE_DENSE=false` turns the embeddings off. See `ml/rag/README.md`.

## Audit trail (decision 37)
Each chat turn stores its audit entries next to the turn record (DynamoDB: same table, `message_id` = `<message id>#audit00`, `#audit01`...; locally the JSONL file, `type: "audit"`). Entry: `event` (`tool_call`, `tool_refused`, `verification`, `handoff`), `outcome` (`ok`, `error`, `no_result`, `not_verified`, `started`, `failed`, `verified`, `locked`, `opened`), `at`, and when they apply `tool`, `args_hash`, `customer` (hash) and `detail` (names of ignored arguments, or the handoff's reason and case id). No text, no raw arguments, no customer ids. After an in-chat verification the same turn also answers the question that started it.

## Session lifetime (decision 36)
A verified session is an idle timeout: every chat turn and every `POST /v1/accounts/overview` renews `verified_until` to now + `VERIFIED_TTL_MINUTES` (30), never beyond `VERIFIED_MAX_HOURS` (8) after `verified_at`. An expired one is not renewed (`401 not_verified`; in the chat, Nova verifies again). The web app keeps the session id in `sessionStorage`, so a reload keeps the customer logged in.

## Account tools (decision 26)
Once the chat session is verified, the model can call `get_my_products`, `get_my_transactions` (`days` 1-365, `status`, `search`, `limit` ≤ 50) and `get_my_complaints` (`status` all/open/closed) (`backend/app/agent/account_tools.py`). None takes a customer id: the backend uses the verified session's customer, so no prompt can reach another customer's data. They read the customer's partition of the demo-customers table (`backend/app/agent/account_data.py`) and return only banking-app fields. Dates are relative to the dataset's last day (`DATA_AS_OF_DATE`). At most 3 tool rounds per turn. Without verification, a tool call starts identity verification instead and reads nothing.

The web app's home page reads the same data through `POST /v1/accounts/overview` (products, the last 30 days' transactions up to 10, open complaints count), also only for the verified session's customer. The session id goes in the body so CloudFront's origin request policy passes it unchanged.

## Handoff to a human agent (decision 27)
The model can call `request_human_agent` (`reason`: customer_request, fraud_or_security, dispute, complaint, unsupported, repeated_failure, other; `summary`; `open_questions`) at any time, verified or not. The backend creates the case (`NB-XXXXXX`): the model's summary and questions, plus the **verified facts** (from the session's verification state) and the **evidence** (the account tool calls and results of this conversation), and the transcript. The reply is fixed text with the case number, and the stream sends a `notice` with `kind: "handoff"` and the case id as `text`.

While the case is `waiting` or `active`, the model isn't called: the customer's messages go to the case (the reply is a short "queued" note while waiting, and empty once an agent is on it). The chat polls `POST /v1/chat/sessions/{id}/handoff` with `after` = the last `next` for the agent's messages and case notices; the session id is the credential and only its own case is returned. When the agent closes the case, the bot answers again, with the agent's messages in the history as context.

**Satisfaction (decision 46).** When the agent closes the case, the chat asks "How was your experience with the advisor?" (1 to 5, optional, shown once per case). `POST /v1/chat/sessions/{id}/handoff/rating` stores `rating` (int) and `rated_at` on the case, one rating per case; the session id is the credential. The console shows `rating` in the case and in the queue, and `stats.satisfaction_avg` (mean of the listed cases' ratings, `null` if none) with `stats.rated` (how many) next to `faithfulness_avg`. The console responses still never carry the customer's `session_id`.

`faithfulness` (decision 28): `{"evidence":[{tool,args,at}],"answers":[{"index","text","claims":[{"token","text","supported"}],"score","sentences":[{"text","similarity":[per evidence item],"shared":[[tokens]]}]}],"overall"}`. `score` and `overall` are supported / total checkable claims, `null` without claims; `similarity` is the cosine of term-frequency vectors (0-1).

The agent console (`/asesor`) uses `POST /v1/agent/...` with the shared demo key (`AGENT_CONSOLE_KEY`) in the body (`401 {"detail":"invalid_key"}` otherwise; unknown case → `404`).

## Identity verification
Before any personal data, the agent verifies the customer (`backend/app/agent/identity.py`, decision 22): document number → date of birth → 6-digit code (demo SMS as a `notice` event). The model can only ask to start it; the answers are handled in code, never sent to the model, and stored as placeholders in the history and the interaction log (`[identity verification input]`). 3 failures lock verification for the session; verification lasts 30 minutes. Demo customers: `docs/demo.md`.

## Interactions (metrics and feedback)
Every turn is recorded before the last event (`done` or `error`) is sent: session, `message_id`, language, question and reply (card/account numbers and emails masked), model, input/output tokens, time to first token and total time, status and error code. Feedback is added to the same record. The backend also logs one JSON line per turn (`turn_metrics`) with the numbers only, no text.

Where it goes depends on `INTERACTIONS_STORE`:
- `jsonl` (default, local): appends to `backend/.interactions/interactions.jsonl` (gitignored).
- `dynamodb` (deployed): table `INTERACTIONS_TABLE`, partition key `session_id` (S), sort key `message_id` (S), TTL attribute `expires_at` (records expire after `INTERACTIONS_TTL_DAYS`).
- `none`: nothing is stored.

## Live metrics (decision 42)
`GET /v1/metrics/live` aggregates every recorded turn for the "Live, from production" section of `/modelos`. Only aggregates: no text, no session or message ids. Audit entries, feedback lines and the spend-limit counters are skipped. DynamoDB: a paginated `Scan` projecting only `session_id` (to count conversations), `status`, `lang`, `channel`, tokens, latencies, `intent`, `intent_confidence`, `created_at` and `type`. Cached in memory for 60 s (`cache_seconds`), so a warm Lambda scans at most once a minute; it never calls the model, so it doesn't count toward the spend limits.

```json
{
  "turns": 120, "conversations": 40,
  "window": {"first": "<iso>", "last": "<iso>"},
  "errors": 3, "error_rate": 0.025,
  "tokens": {"input_per_conversation": 3812.5, "output_per_conversation": 210.2},
  "cost": {"per_conversation": 0.004863, "per_1000_conversations": 4.863, "per_1000_turns": 1.621,
           "price_per_mtok": {"input": 1.0, "output": 5.0}},
  "latency_ms": {"total": {"p50": 2400, "p95": 6100, "n": 117},
                 "first_token": {"p50": 900, "p95": 2100, "n": 117}},
  "intent": {"classified": 100, "distribution": {"other": 70, "complaint": 30},
             "confident_share": 0.62, "threshold": 0.58},
  "by_lang": {"es": {"turns": 80, "conversations": 25}, "pt": {"turns": 40, "conversations": 15}},
  "by_channel": {"account": {"turns": 90, "conversations": 30}, "public": {"turns": 30, "conversations": 10}},
  "faithfulness": {"cases": 12, "scored": 10, "mean": 0.91,
                   "claims": {"supported": 52, "total": 58, "rate": 0.897},
                   "buckets": {"all": 7, "most": 2, "low": 1},
                   "window": {"first": "<iso>", "last": "<iso>"}, "limit": 50},
  "satisfaction": {"rated": 4, "mean": 4.25, "distribution": {"1": 0, "2": 0, "3": 1, "4": 1, "5": 2},
                   "window": {"first": "<iso>", "last": "<iso>"}},
  "generated_at": "<iso>", "cache_seconds": 60
}
```

`satisfaction` (decision 46) covers every rated case (window: first and last `rated_at`); `mean` is `null` with no ratings. DynamoDB: a `Scan` of the cases table projecting only `rating` and `rated_at` (stored as top-level attributes next to the case JSON), never the case text. It is the same `Scan` the console's queue already uses: no new IAM permission.
`faithfulness` scores the last `limit` handed-over cases with the agent console's check (decision 28): the share of checkable claims in Nova's answers (amounts, dates, last digits, names) found in the data it consulted. `scored` counts the cases with at least one claim; `buckets`: every claim found, 75-99%, under 75%. Only the scores: never the answers, case ids or names.
Ratios and per-conversation values are `null` when there are no turns; percentiles are nearest-rank over the turns that reported the latency (`n`). Cost uses `LLM_PRICE_INPUT_PER_MTOK` / `LLM_PRICE_OUTPUT_PER_MTOK`; `threshold` is the intent model's confidence threshold.

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
| `CUSTOMER_DIRECTORY` | backend | `demo` (default: 2 fictional customers) or `dynamodb` (deployed: the whole dataset, loaded by `data/scripts/load_demo_data.py`) |
| `DATA_AS_OF_DATE` | backend | "Today" for the account tools: the dataset's last day. Default `2026-06-17` |
| `CASES_STORE` | backend | `memory` (default, local) or `dynamodb` (deployed): handoff cases |
| `CASES_TABLE` | backend | DynamoDB table for `dynamodb`. Default `fh26-handoff-cases` |
| `CASE_TTL_DAYS` | backend | Days a case is kept. Default `7` |
| `AGENT_CONSOLE_KEY` | backend | Key of the human agent console. Default `Asesor2026` (public demo value) |
| `DEMO_PASSWORD` | backend | The password every demo customer logs in with. Default `Nova2026` (public, documented) |
| `CUSTOMERS_TABLE` | backend | DynamoDB table for `dynamodb`. Default `fh26-demo-customers` |
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
