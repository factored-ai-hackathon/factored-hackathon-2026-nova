# evals

Evaluation sets and harness (Evaluation-Driven Development). Owner: Miguel.

Every capability ships with its eval set, in Spanish and Portuguese:
- `agent/`: intent routing, answer quality, RAG grounding, structured output validity
- `security/`: skipping identity verification, requesting another customer's data, prompt injection, forcing prohibited actions
- `ml/`: contact center model metrics on held-out data
- `reliability/`: tool/LLM failures, timeouts, malformed outputs, escalation

Reported results run against Bedrock (the production provider). Eval cases use synthetic data only.

## Run
From `backend/`: `uv run pytest ../evals/agent`. It uses a fake model by default (no token, no cost), which checks the harness and the graph. `EVAL_LIVE=1` runs the cases against the configured provider.

| Set | Cases | Checks |
|---|---|---|
| `agent/smoke.yaml` | 10 (5 ES, 5 PT) | Reply language; never asks for card number/PIN/password; no invented amounts |
| `agent/identity.yaml` | chat verification flows (ES, PT) | Verification step after each message; demo SMS; answers never repeated |
| (faithfulness) | `backend/tests/test_faithfulness.py` | Claims found / not found in the evidence, number normalization, sentence-to-evidence similarity; shown per case in the agent console |
| `agent/handoff.yaml` | 7 (4 ES, 3 PT) | Hands over when it should (person, fraud, stolen card) with code-built facts; asks when ambiguous; never claims an unsupported action was done |
| `agent/account_tools.yaml` | 8 (5 ES, 3 PT) | Data read only for the session's customer and never before verification; the right tool; amounts and facts from the tool; nothing from other customers (incl. injection) |
