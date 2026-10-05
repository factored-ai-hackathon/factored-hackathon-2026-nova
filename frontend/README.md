# NovaBank frontend

Customer-facing banking demo with the Nova AI assistant (Spanish and Portuguese). Banking data and login are simulated; the Nova chat talks to the real backend. Owner: Miguel.

Vite + React + TypeScript. Chat API contract: [docs/api-contract.md](../docs/api-contract.md).

## Run locally

Needs Node.js 20.19+ (Mac: `brew install node`, Windows: `winget install OpenJS.NodeJS.LTS`).

```sh
cd frontend
npm install
npm run dev              # http://localhost:5173, proxies /v1 to the backend on :8000
```

Start the backend first (see [backend/README.md](../backend/README.md)). No backend? Use the mock agent:

```sh
VITE_MOCK=1 npm run dev                                # Mac
$env:VITE_MOCK="1"; npm run dev                        # Windows PowerShell
```

Use any email-shaped value and a non-empty password on the demo login screen. Optional settings go in `frontend/.env.local` (see `.env.example`). `VITE_*` values are bundled into the app, so never put secrets there.

## Checks

```sh
npm run build
npm test
npm run lint
```

## Demo flow

Login → dashboard → transaction details → ask Nova → review the full conversation and agent metadata → try the mocked human escalation controls. The dashboard also opens Nova from its floating assistant button.

## Frontend/backend boundary

| Path | What |
|---|---|
| `src/api/client.ts` | Create a session, POST a message and read the SSE stream (`fetch` + `ReadableStream`) |
| `src/services/agentService.ts` | What the UI calls. Real mode streams replies from the backend; `VITE_MOCK=1` uses keyword-based mock replies |
| `src/services/authService.ts`, `src/data/` | Mock login, customer, account, card and transaction data |

The MVP backend returns only the reply text, so intent, sentiment and confidence show as empty in real mode. When the customer asks Nova about a selected transaction, its merchant, amount and date are sent as a prefix of the message. The proposed richer contract (intent, sentiment, escalation) is in [docs/agent-api-contract.md](docs/agent-api-contract.md).
