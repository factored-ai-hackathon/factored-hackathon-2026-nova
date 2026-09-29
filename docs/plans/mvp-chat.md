# MVP chat plan (director brief)

**Branch:** `Ftd/mpv_chat`, created from `development` (same commit as `main` today). PR back into `development`.
**Goal:** a working chat that answers in Spanish or Portuguese. It runs end to end on a laptop: React → FastAPI → LangChain/LangGraph → a free Hugging Face model. The team keeps building on this base (auth, RAG, tools, Bedrock, deploy).

## How the director runs this
1. Create `Ftd/mpv_chat`, commit this file and the **contract** below (`docs/api-contract.md`). Executors code against the contract, not against each other.
2. Launch executors E1–E3 in parallel. Each works in its **own git worktree**, on a sub-branch (`Ftd/mpv_chat-api`, `-llm`, `-web`). Each touches only its folders.
3. When E1–E3 are green, merge the sub-branches into `Ftd/mpv_chat` and run E4 (integration). Then open the PR.
4. Every executor prompt includes the repo rules in `CLAUDE.md`: no secrets in code, no push to `main`, and only synthetic/test text goes to Hugging Face.

## Scope
**In:** chat UI, streaming API, in-memory sessions, a swappable LLM layer, ES/PT replies, tests that pass without a token, run-locally docs.
**Out (next iterations):** identity check (KBA/OTP), RAG, DynamoDB tools, intent classifier, Bedrock, Terraform/deploy. Leave clearly marked extension points instead.

## Contract (shared by all executors)
| Endpoint | Request | Response |
|---|---|---|
| `GET /health` | – | `{"status":"ok","llm_provider":"huggingface"}` |
| `POST /v1/chat/sessions` | `{"lang":"es"\|"pt"}` (optional, default `es`) | `201 {"session_id":"<uuid>","lang":"es"}` |
| `POST /v1/chat/sessions/{id}/messages` | `{"text":"...","lang":"es"\|"pt"}` | `text/event-stream` with events `token` `{"text":"..."}`, `done` `{"message_id":"..."}`, `error` `{"code":"...","message":"..."}` |

Unknown session → `404`. Empty or >2,000-char text → `422`.
Python seam between API and agent (in `backend/app/agent/__init__.py`):
`async def stream_reply(session_id: str, text: str, lang: str) -> AsyncIterator[str]`

**Env vars** (names only; values in `backend/.env`, gitignored): `APP_ENV`, `LLM_PROVIDER` (`huggingface` | `bedrock`), `HF_TOKEN`, `HF_MODEL_ID`, `HF_BASE_URL` (default `https://router.huggingface.co/v1`), `CORS_ORIGINS`. Frontend: `VITE_API_URL`.

## Executors

### E1 – Backend API (`backend/`, except `app/agent` and `app/llm.py`)
- New uv project `backend/pyproject.toml` (Python 3.12): fastapi, uvicorn, pydantic-settings, sse-starlette; dev: pytest, httpx, ruff. Kept separate from the root data/ML project so the image stays small.
- `app/main.py` (app, CORS, `/health`), `app/config.py` (settings), `app/api/chat.py` (sessions and SSE per the contract), `app/sessions.py` (in-memory store behind an interface, so DynamoDB can replace it later).
- Until E2 lands, use a stub `stream_reply` that echoes word by word.
- Tests: the contract's happy path, 404, 422, and SSE event order.

### E2 – LLM + agent layer (`backend/app/llm.py`, `backend/app/agent/`)
- `get_chat_model()` reads `LLM_PROVIDER`:
  - `huggingface`: `langchain_openai.ChatOpenAI` pointed at the HF router's OpenAI-compatible API (`base_url=HF_BASE_URL`, `api_key=HF_TOKEN`, `model=HF_MODEL_ID`). This gives streaming and tool calling through one well-supported client. `langchain-huggingface`'s `ChatHuggingFace` is the alternative if we want it later.
  - `bedrock`: `langchain_aws.ChatBedrockConverse` stub, not exercised yet.
  - Guard: if `APP_ENV=prod` and the provider isn't `bedrock`, refuse to start.
- Model: default `HF_MODEL_ID=openai/gpt-oss-20b`. Before committing it, verify it is served by an Inference Provider and supports streaming and tools. Fallbacks to check: `Qwen/Qwen2.5-7B-Instruct`, `meta-llama/Llama-3.1-8B-Instruct`.
- Minimal LangGraph graph: one `respond` node with a system prompt per language (`prompts/es.md`, `prompts/pt.md`: bank contact-center assistant, answers only in the user's language, never asks for passwords/card numbers, says it can't see account data yet). Session memory comes from the `MemorySaver` checkpointer with `thread_id = session_id`.
- Mark where the next nodes go (`classify_turn`, `auth_gate`, `answer_public`, `handoff`) with TODO comments only; don't build them.
- Tests use LangChain's `GenericFakeChatModel`, so there's no network or token in CI. One opt-in live test runs only when `HF_TOKEN` is set.

### E3 – Frontend (`frontend/`)
- Vite + React + TypeScript. Components: `ChatWindow`, `MessageBubble`, `Composer`, `LanguageToggle` (ES/PT, also sets `lang` on the session). Strings live in `src/i18n/es.json` and `pt.json`.
- `src/api/client.ts`: create a session, then POST a message and read the SSE stream with `fetch` + `ReadableStream` (EventSource can't POST). Render tokens as they arrive; show errors inline; disable send while streaming.
- Vite dev proxy `/v1` → `http://localhost:8000`. Add a mock mode (`VITE_MOCK=1`) that fakes the stream, so UI work doesn't need the backend.
- Plain CSS or CSS modules, no UI kit. Must work at phone width.

### E4 – Integration (after merge)
- Replace E1's stub with E2's `stream_reply`. Run both apps and do one manual chat in ES and one in PT.
- `evals/agent/smoke.yaml`: 10 cases (5 ES, 5 PT). Check the answer's language, refusal to ask for card number/PIN, and no invented balances. Add a pytest runner that uses the fake model by default.
- Fill `Run locally` and `Tests` in `CLAUDE.md`, and update `backend/README.md` and `frontend/README.md`.
- Add row 16 to `docs/decisions.md`: MVP uses Hugging Face Inference Providers (free tier) for local development, which replaces OpenRouter there; production stays Bedrock only; only synthetic/test text is sent to HF.

## Definition of done
- `cd backend && uv run uvicorn app.main:app --reload` and `cd frontend && npm run dev` → a streamed reply in the chosen language.
- `uv run pytest` and `uv run ruff check` pass in `backend/` with no `HF_TOKEN`. `npm run build` and `npm run lint` pass in `frontend/`.
- No secrets, tokens or dataset records in the diff. `.env.example` lists the new variable names.
- PR `Ftd/mpv_chat` → `development` with a short description and screenshots.

## Known risk
The HF free tier is **$0.10 of credits per month per account** ([pricing](https://huggingface.co/docs/inference-providers/pricing)). That's enough for smoke tests with a small model, not for eval runs. Keep tests on the fake model, run live chats sparingly, and plan the switch to Bedrock before running full evals.
