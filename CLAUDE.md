# Factored Hackathon 2026 — AI-first Banking Agent

## What we are building
An "AI-first" banking agent focused on **a single flow** done well, working in **Spanish and Portuguese**.

**Focus: Contact Center Optimization** (use case from the LATAM Bank dataset):
- **First Call Resolution (FCR)** improvement
- **Agent performance** analysis and benchmarking
- **Sentiment trend** analysis

The credit-eligibility agent (XGBoost credit scoring, amortization tables) from the earlier design is **out of scope**.

Challenge deliverables (deadline **October 5, 2026**):
- Deployed, working link
- Public GitHub repository (this one)
- 4–6 slide presentation
- Video pitch

Challenge details and timeline: @docs/challenge.md

## Constraints that guide every decision
- **Minimum cost**: the team pays for the infrastructure. Everything should be serverless or scale-to-zero where possible. Justify the cost before adding any AWS service.
- **ML used with judgment**: the judges value machine learning applied where it adds value, not as decoration.
- **Security first**: never expose personal data before verifying identity, and never another user's data.
- **Evaluation-Driven Development**: every agent capability ships with its evaluation set, before or together with the implementation.

## Architecture (summary)
- Agent built with **LangGraph** (router / admin graph that enforces the security steps in code) and **LangChain** (models, tools, prompts)
- LLM provider chosen by config: **Amazon Bedrock** (Claude) in production; **Hugging Face Inference Providers** (free tier) for local development only
- **Identity verification** (KBA + OTP) before revealing any personal data
- **RAG** over a knowledge base of products/policies
- **Query tools** over DynamoDB
- **Contact center ML** where it adds value, trained on the call center, transcript, survey and complaint data (e.g. predicting whether a contact will be resolved on the first call, sentiment trends, agent benchmarking). Exact models to be defined.
- **Hooks** that block prohibited actions before they run
- **Guardrails** against access to other users' data
- **Human escalation** for ambiguous or high-risk cases
- **FastAPI** backend; Lambdas chained with **SQS**; containers on **ECS**
- Infrastructure as code with **Terraform**
- Data: ~19M records → data lake in **S3**: original gzipped CSV in the `data-root` bucket, cleaned Parquet in `curated/` of the `hackaton-data` bucket, cleaned with **Athena** SQL (Glue Data Catalog for table definitions), before training

Details: @docs/architecture.md

## Repository structure
- `infra/`: Terraform (`infra/data-lake/` for S3, Glue catalog, Athena)
- `docs/`: architecture, challenge, decision log (`decisions.md`), setup guide (`setup.md`)
- `frontend/`: chat UI
- `backend/`: FastAPI and the agent
- `ml/`: contact center models
- `evals/`: evaluation sets and harness (agent, ML, security)
- `data/`: data pipeline code (upload script, Athena cleaning SQL). No dataset files.

## Team and responsibilities
- **Miguel**: coordination, QA / reliability / evaluation; co-platform; co-frontend
- **Esteban**: architecture; co-backend; co-frontend
- **Paul**: backend (with Esteban); platform; Agent AI; data and ML

## AWS environment
- Dedicated member account inside a separate AWS Organization, used only for the hackathon.
- Team access through **IAM users with personal access keys** in the `hackaton-team` group (set up manually by Paul). One key per person, never shared or committed; keys are deleted after the hackathon (Oct 16, 2026).

## Rules for Claude Code in this repo
- **Never** write secrets, tokens, account IDs or credentials in code, docs or commits. Use `.env` (ignored by git) or environment variables / Secrets Manager; document only the variable *name*.
- **Never** delete files, resources or data without explicit confirmation. No `terraform destroy`, `rm -rf`, or deleting buckets/tables without asking.
- Before a `terraform apply`, show the `plan` and wait for approval.
- **Branches:** `development` is the long-lived integration branch; `main` is production. Branch from `development` and open PRs into `development`. Never push to `main` or `development` directly, and never delete `development`.
- **Releases:** only `development` goes into `main` (`.github/workflows/release-guard.yml` fails any other PR into `main`). A PR from `development` to `main`, merged with a merge commit (no squash/rebase, so the branches don't drift). Every push to `main` runs `.github/workflows/deploy.yml` (tests, then Lambda + S3/CloudFront deploy, then a GitHub release named after the date: `vYYYY.MM.DD`, `.2`, `.3`... for more releases the same day).
- The repo is **public**: do not commit dataset data, PII or samples of real records.
- **Production uses only Bedrock.** Hugging Face is for local development: send it only synthetic dataset records or test data, never secrets, credentials or real personal data.

## Commands
- Setup (Mac and Windows): see `docs/setup.md`
- Install dependencies (from `pyproject.toml`): `uv sync`
- Run any Python tool: `uv run <tool>` (e.g. `uv run jupyter lab`)
- Build the data model: `uv run dbt build` (from `data/dbt`)
- Add a library: `uv add <package>` (updates `pyproject.toml` and `uv.lock`; commit both)
- Tests (from `backend/`, no token needed): `uv run pytest` and `uv run ruff check`
- Frontend checks (from `frontend/`): `npm run build`, `npm test` and `npm run lint`
- Agent evals (from `backend/`): `uv run pytest ../evals/agent` (fake model by default; `EVAL_LIVE=1` uses the real one)
- Run locally: `uv run uvicorn app.main:app --reload --reload-dir app` (from `backend/`) and `npm run dev` (from `frontend/`), then open http://localhost:5173
- Chat API contract: `docs/api-contract.md`
- Terraform (data lake): `terraform -chdir=infra/data-lake plan`

# AWS Guidance

- Where these AWS rules conflict with the project's own instructions, the
  project's instructions take precedence.
- Prefer the AWS MCP Server for AWS interactions — it provides sandboxed
  execution, observability, and audit logging. If unavailable, use the
  AWS CLI directly.
- Before starting a task, check whether a relevant AWS skill is available.
  Load the skill with `retrieve_skill` and prefer its guidance over
  general knowledge.
- When uncertain about specific AWS details (API parameters, permissions,
  limits, error codes), verify against documentation rather than guessing.
  State uncertainty explicitly if you cannot confirm.
- When creating infrastructure, prefer infrastructure-as-code (AWS CDK or
  CloudFormation) over direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework
  principles.
- Do not use em dashes in AWS resource names or descriptions. Use
  hyphens instead.

## Secret Safety

- MUST load the `aws-secrets-manager` skill first for any secret,
  credential, API key, token, or password task. MUST NOT call
  `secretsmanager get-secret-value` or `batch-get-secret-value`, and MUST
  NOT hit the Secrets Manager Agent daemon directly. MUST use
  `{{resolve:secretsmanager:secret-id:SecretString:json-key}}` with
  `asm-exec` so the secret resolves at runtime without entering context.
<!-- END AWS Agent Toolkit rules -->
