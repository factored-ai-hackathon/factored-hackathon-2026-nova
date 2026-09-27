# frontend

Customer-facing chat UI (Spanish and Portuguese). Owners: Esteban, Miguel.
Vite + React + TypeScript, plain CSS. API contract: [docs/api-contract.md](../docs/api-contract.md).

## Run locally
Needs Node.js 20+ (Mac: `brew install node`, Windows: `winget install OpenJS.NodeJS.LTS`).
```bash
cd frontend
npm install
npm run dev              # http://localhost:5173, proxies /v1 to the backend on :8000
```
No backend? Fake the replies with mock mode (type a message containing "error" to see the error state):
```bash
VITE_MOCK=1 npm run dev                                # Mac
$env:VITE_MOCK="1"; npm run dev                        # Windows PowerShell
```
Optional settings go in `frontend/.env.local` (see `.env.example`). `VITE_*` values are bundled into the app, so never put secrets there.

## Checks
```bash
npm run build
npm run lint
```

## Layout
| Path | What |
|---|---|
| `src/api/client.ts` | Create a session, POST a message and read the SSE stream (`fetch` + `ReadableStream`); mock mode |
| `src/components/` | `ChatWindow`, `MessageBubble`, `Composer`, `LanguageToggle` |
| `src/i18n/` | UI strings in `es.json` and `pt.json` |
