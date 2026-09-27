# MVP chat: run and test it step by step

A hands-on checklist to get the MVP chat talking to the real model on your Mac, test it, then commit and open the PR.
Every step says what you should see. If a step fails, jump to [Troubleshooting](#troubleshooting).

Branch: `Ftd/mvp_chat`. The plan committed in `3758aa0` is already on it.

---

## 0. Prerequisites (once)

```bash
uv --version     # any recent version; uv installs Python 3.12 for backend/ by itself
node -v          # v20 or newer
```
Missing Node: `brew install node`. Missing uv: see `docs/setup.md`.

## 1. Get a Hugging Face token (once)

1. Sign in at https://huggingface.co and go to **Settings → Access Tokens → Create new token**.
2. Choose **Fine-grained** and tick **"Make calls to Inference Providers"**. Nothing else is needed.
3. Copy the token (it starts with `hf_`). Treat it like a password.

> The free tier gives **$0.10 of credits per month**. That's plenty for manual chats with `gpt-oss-20b`, but don't loop live evals.

## 2. Configure the backend (once)

```bash
cd backend
cp .env.example .env
open -e .env          # paste the token after HF_TOKEN=, save, close
git check-ignore -v .env
```
✅ The last command prints a line ending in `.gitignore:...:.env`, which means git will never commit the file.

## 3. Offline checks (no token used)

```bash
# still in backend/
uv sync
uv run pytest            # expect: 40 passed, 1 skipped
uv run ruff check        # expect: All checks passed!

cd ../frontend
npm install
npm run build && npm run lint   # expect: no errors
```
This is the baseline. If it's red here, the problem isn't the model.

## 4. Start the backend

Terminal 1:
```bash
cd backend
uv run uvicorn app.main:app --reload
```
✅ `Uvicorn running on http://127.0.0.1:8000`. Keep this terminal visible: **errors from the model are logged here**.

Terminal 2:
```bash
curl -s http://localhost:8000/health
```
✅ `{"status":"ok","llm_provider":"huggingface"}`. You can also browse http://localhost:8000/docs.

## 5. Test the API with curl (first real model call)

Still in terminal 2. Create a Spanish session and keep its id:
```bash
SID=$(curl -s -X POST http://localhost:8000/v1/chat/sessions \
  -H 'Content-Type: application/json' -d '{"lang":"es"}' \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["session_id"])')
echo $SID
```
Send a message and watch the stream (`-N` turns off buffering):
```bash
curl -N -X POST http://localhost:8000/v1/chat/sessions/$SID/messages \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hola, ¿qué puedes hacer por mí?"}'
```
✅ Several `event: token` lines with Spanish text, then **one** `event: done`.
❌ `event: error` with `llm_error` → look at terminal 1 and the [Troubleshooting](#troubleshooting) table.

`gpt-oss` reasons before it answers, so a few seconds with no output before the first token is normal.

**Memory check** (same session):
```bash
curl -N -X POST http://localhost:8000/v1/chat/sessions/$SID/messages \
  -H 'Content-Type: application/json' -d '{"text":"¿Qué te pregunté hace un momento?"}'
```
✅ It refers to your first question.

**Portuguese** (switch the language on the same session):
```bash
curl -N -X POST http://localhost:8000/v1/chat/sessions/$SID/messages \
  -H 'Content-Type: application/json' -d '{"text":"Olá, esqueci a senha do meu cartão","lang":"pt"}'
```
✅ Reply in Portuguese, and it does **not** ask you for the PIN/password.

**Contract errors** (no model call):
```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8000/v1/chat/sessions/nope/messages \
  -H 'Content-Type: application/json' -d '{"text":"hola"}'          # expect 404
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8000/v1/chat/sessions/$SID/messages \
  -H 'Content-Type: application/json' -d '{"text":"   "}'            # expect 422
```

## 6. Test the chat UI

Terminal 2 (the backend keeps running in terminal 1):
```bash
cd frontend
npm run dev
```
Open http://localhost:5173.

| # | Do | Expect |
|---|---|---|
| 1 | Type *"Hola, ¿qué puedes hacer por mí?"* | The reply streams in word by word; Send is disabled while streaming |
| 2 | Ask *"¿Cuánto dinero tengo en mi cuenta?"* | It says it can't see account data yet, with no invented amounts |
| 3 | Switch the toggle to **PT**, type *"Olá, em que você pode me ajudar?"* | UI strings and the reply are in Portuguese |
| 4 | Stop the backend (Ctrl+C in terminal 1), send a message | An inline error, and the UI doesn't hang. Restart the backend afterwards |
| 5 | DevTools → device toolbar → iPhone width | Layout fits, no horizontal scroll |

📸 Take the PR screenshots here: one ES chat, one PT chat, one at phone width.

Optional, UI without backend or credits: `VITE_MOCK=1 npm run dev` (type "error" to see the error state).

## 7. Live automated tests (optional, uses a few credits)

From `backend/`. The live test is skipped unless `HF_TOKEN` is in the environment, so load `.env` in a subshell to keep the token out of your shell history:
```bash
(set -a; source .env; set +a; uv run pytest -m live)                  # 1 call
(set -a; source .env; set +a; EVAL_LIVE=1 uv run pytest ../evals/agent)  # 10 calls
```
✅ `1 passed`, and the 10 smoke cases pass. A failure in the eval run is useful: the model broke a rule (wrong language, asked for a PIN, stated an amount). Note the case id in the PR rather than loosening the check.

## 8. Production guard (10 seconds)

```bash
APP_ENV=prod uv run uvicorn app.main:app
```
✅ It **refuses to start** with `APP_ENV=prod only allows LLM_PROVIDER=bedrock`. That's the intended behavior.

## 9. Commit and open the PR

**Branch name.** Keep `Ftd/mvp_chat`: that's the correct spelling. The plan file had a typo (`mpv`); fix it so the docs match:
```bash
cd ..   # repo root
sed -i '' 's/mpv_chat/mvp_chat/g' docs/plans/mvp-chat.md
```

**Check what goes in.** Nothing from `.env`, `node_modules`, `.venv` or `dist`:
```bash
git status
git add CLAUDE.md backend docs evals frontend
git diff --cached --stat
git diff --cached | grep -nE 'hf_[A-Za-z0-9]{20,}' || echo "OK: no HF tokens staged"
git diff --cached --name-only | grep -E '(^|/)\.env$' || echo "OK: no .env staged"
```

**Commit and push:**
```bash
git commit -m "MVP chat: FastAPI SSE API, LangGraph agent on HF, React UI, smoke evals"
git push -u origin Ftd/mvp_chat
```

**PR** into `development`. Use the GitHub "Compare & pull request" banner, or:
```bash
gh pr create --base development --head Ftd/mvp_chat --title "MVP chat (ES/PT) end to end"
```
Paste into the PR body:
- [ ] `uv run pytest`: 40 passed, 1 skipped (offline)
- [ ] `ruff check`, `npm run build`, `npm run lint` green
- [ ] Live chat ES ✅ / PT ✅ (screenshots)
- [ ] Live smoke eval: x/10 passed
- [ ] Known gaps: Bedrock raises `NotImplementedError`; auth, RAG, DynamoDB and handoff are TODOs in `backend/app/agent/graph.py`

---

## Troubleshooting

The real error is always in **terminal 1** (the backend log). The chat only shows a generic `llm_error`.

| Symptom (backend log) | Likely cause | Fix |
|---|---|---|
| `HF_TOKEN is not set` | `.env` missing or the token isn't saved | Check `backend/.env`, then **restart** uvicorn (`--reload` doesn't watch `.env`) |
| `401` / `Invalid credentials` | Token mistyped or revoked | Create a new token, paste it again |
| `403` | Token lacks the Inference Providers permission | Edit the token and tick "Make calls to Inference Providers" |
| `402` / payment required | Free monthly credits used up | Wait for the monthly reset or add credits; test the UI with `VITE_MOCK=1` meanwhile |
| `model not supported` / `404` for the model | No provider serving it right now | Pin a provider, e.g. `HF_MODEL_ID=openai/gpt-oss-20b:groq` (any provider listed on the model page), or try `Qwen/Qwen2.5-7B-Instruct`; restart |
| Browser console shows a CORS error | UI isn't on `localhost:5173` | Add its origin to `CORS_ORIGINS` in `.env` and restart |
| `Address already in use` | Something else is on :8000 | `lsof -i :8000`, stop it, or run with `--port 8001` and update the proxy in `vite.config.ts` |
| First token takes several seconds | `gpt-oss` reasons first | Normal. If it's too slow for the demo, try a non-reasoning model via `HF_MODEL_ID` |
