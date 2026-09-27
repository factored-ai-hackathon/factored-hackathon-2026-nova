# NovaBank frontend draft

Customer-facing banking demo and AI contact-center UI. All banking data and login are simulated; there are no real transactions or backend connections. Owners: Esteban, Miguel.

## Run locally

```sh
npm install
npm run dev
```

Use any email-shaped value and a non-empty password on the demo login screen. To validate the frontend:

```sh
npm run build
npm test
npm run lint
```

## Demo flow

Login → dashboard → transaction details → ask Nova → review the full conversation and safe agent metadata → try the mocked human escalation controls. The dashboard also opens Nova from its floating assistant button.

## Frontend/backend boundary

Presentation components call the typed mock services in `src/services/`; mock customer, account, card, and transaction data is in `src/data/`. Replace the service implementations when the backend is ready. The proposed request/response fields and EDD metadata are documented in [docs/agent-api-contract.md](docs/agent-api-contract.md). Transaction context is forwarded when the customer asks Nova about a selected transaction. Internal chain-of-thought is not part of the UI contract.

Spanish and Portuguese are represented by the `Language` type and translation catalog. The mock agent returns localized responses for common demo intents. Some banking labels and dashboard content remain Spanish-only in this draft.
