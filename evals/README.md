# evals

Evaluation sets and harness (Evaluation-Driven Development). Owner: Miguel.

Every capability ships with its eval set, in Spanish and Portuguese:
- `agent/`: intent routing, answer quality, RAG grounding, structured output validity
- `security/`: skipping identity verification, requesting another customer's data, prompt injection, forcing prohibited actions
- `ml/`: contact center model metrics on held-out data
- `reliability/`: tool/LLM failures, timeouts, malformed outputs, escalation

Reported results run against Bedrock (the production provider). Eval cases use synthetic data only.
