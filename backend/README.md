# backend

API (FastAPI) and the agent (LangGraph + LangChain). Owners: Paul, Esteban (API); Paul, Iris (agent).
Separate uv project from the root data/ML one, so the image stays small. API contract: [docs/api-contract.md](../docs/api-contract.md).

## Run locally
```bash
cd backend
uv sync
cp .env.example .env        # then set HF_TOKEN (see below)
uv run uvicorn app.main:app --reload --reload-dir app
```
API on http://localhost:8000 (interactive docs at `/docs`). Start the frontend too (see `frontend/README.md`).

**No token, no AWS:** `LLM_PROVIDER=fake uv run uvicorn app.main:app --reload --reload-dir app` streams a fixed reply in Spanish or Portuguese (it echoes your message). Everything else works as usual: sessions, streaming, interactions and 👍/👎. Useful for UI work; dev only.

**Local LLM:** create a personal Hugging Face token (fine-grained, permission "Make calls to Inference Providers") and put it in `backend/.env` as `HF_TOKEN`. The free tier is only $0.10 of credits per month, so chat sparingly. Send only test text, never real customer data. Production uses Bedrock; with `APP_ENV=prod` the app refuses to start with any other provider.

**Bedrock:** `LLM_PROVIDER=bedrock` uses Claude Haiku 4.5 (`BEDROCK_MODEL_ID`, default `us.anthropic.claude-haiku-4-5-20251001-v1:0`, a US cross-Region inference profile) in `AWS_REGION` (default `us-east-2`). AWS credentials come from the standard chain: the service's IAM role in production, your AWS profile locally (`AWS_PROFILE=hackathon`). The account needs model access for Claude Haiku 4.5, and the role needs `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` on the inference profile and the model in the US Regions it routes to. `BEDROCK_LIVE=1 uv run pytest -m live` sends one test message.

Without `HF_TOKEN` the API still runs, but each message ends with an `error` event (use `LLM_PROVIDER=fake` instead).

## Tests
```bash
uv run pytest            # API, agent (fake model) and the smoke eval in ../evals/agent
uv run ruff check
uv run ruff format
```
No token or network needed. `HF_TOKEN=... uv run pytest -m live` runs the one live test.

## Layout
| Path | What |
|---|---|
| `app/main.py` | App, CORS, `/health`, prod provider guard at startup |
| `app/config.py` | Settings from env vars / `.env` |
| `app/api/chat.py` | Sessions and SSE streaming (see the contract) |
| `app/sessions.py` | Sessions and conversation history: in memory locally, DynamoDB deployed (`SESSIONS_STORE`) |
| `app/interactions.py` | Records each turn (masked text, tokens, latency, errors) and its 👍/👎 feedback |
| `app/llm.py` | Chat model per `LLM_PROVIDER` |
| `app/agent/` | `stream_reply` seam, LangGraph graph, system prompts per language |

## Interactions and feedback
Every chat turn and its 👍/👎 rating are recorded (contract: `docs/api-contract.md`). Locally they go to `backend/.interactions/interactions.jsonl` (gitignored); deployed, to DynamoDB (`INTERACTIONS_STORE=dynamodb`). Card/account numbers and emails are masked before storing. Replies rated 👎 are candidates for new cases in `evals/agent/smoke.yaml`.

Quick look at the local file:
```bash
tail -n 5 .interactions/interactions.jsonl
```

The next graph nodes (`classify_turn`, `auth_gate`, `answer_public`, `handoff`) are marked with TODOs in `app/agent/graph.py`.
