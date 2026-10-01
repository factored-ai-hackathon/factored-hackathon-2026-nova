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
| `ml/intent/data/test_*.jsonl` | 210 (105 ES, 105 PT), team-written | Intent classifier on held-out phrases: macro-F1 vs keyword and majority baselines, per language and class, calibration (`uv run python ml/intent/train.py`, results in `ml/intent/metrics.json`) |
| (faithfulness) | `backend/tests/test_faithfulness.py` | Claims found / not found in the evidence, number normalization, sentence-to-evidence similarity; shown per case in the agent console |
| `agent/handoff.yaml` | 9 (5 ES, 4 PT) | Hands over when it should (person, fraud, stolen card) with code-built facts; asks when ambiguous; never claims an unsupported action was done; complaint and retention: the intent is kept in code and Nova offers a person |
| `agent/public.yaml` | 10 (6 ES, 4 PT) | Public assistant: right hours, addresses and WhatsApp number per country; sends account questions to the login; nothing about customers; refuses off-topic |
| `agent/account_tools.yaml` | 8 (5 ES, 3 PT) | Data read only for the session's customer and never before verification; the right tool; amounts and facts from the tool; nothing from other customers (incl. injection) |
| `agent/knowledge.yaml` | 16 (8 ES, 8 PT) | Knowledge search: answers a policy question from the documents (right figure, source named, search tool used); says it doesn't know and offers a person when the documents don't answer. Retrieval itself: `ml/rag` (recall@k, MRR vs baselines) |
| `agent/language_switch.yaml` | 2 conversations (10 messages) | The customer switches language mid-conversation: every reply is in the language of its own message (decision 33) |

## Held-out evaluation report (`report/`)
`report/REPORT.md` is the evaluation the challenge asks for: 60 team-generated synthetic cases (30 ES, 30 PT) through the real agent on Bedrock, 3 repetitions each, measuring safe automated resolution, containment, escalation quality, unsafe outcomes, p50/p95 latency and cost per case, by language, with the data labeled. `report/cases.yaml` (the cases), `metrics.py` (scoring in code, tested), `run_report.py` (the runner), `render.py` (writes the report from `report/results/*.json`; the numbers are never typed by hand). Run 1 is the held-out measurement; run 2 repeats the same cases after the fixes run 1 led to. From `backend/`: `uv run python ../evals/report/run_report.py --repeats 3`, then `render.py`.

## Load and prompt injection (`load/`)
`load/locustfile.py` drives the deployed API through the real flow (scenarios → login → code → chat). `ChatUser` measures latency per request (plus time to first token and total time of each streamed turn); `InjectionUser` sends 12 ES/PT injection payloads (ignore-rules, fake system message, other customer's id/document, tool-parameter injection, PIN request, skip-verification, base64, oversize) and fails when a reply leaks the other customer's data or a system-prompt line, asks for PIN/password, or states amounts before verification. Run: `cd evals/load && uvx locust -f locustfile.py --host <url> --users 5 --spawn-rate 1 --run-time 3m --headless --csv results/run`. Keep it small on production: it spends the app's daily budget and hits the per-IP rate limit (429s are reported separately).
