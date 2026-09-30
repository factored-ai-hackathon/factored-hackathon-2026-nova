# Architecture

> Summary. Esteban's architecture document is the main reference.

## What the agent does
1. The customer writes in Spanish or Portuguese.
2. **Identity check**, enforced in code (`backend/app/agent/identity.py`): the web login (document + password, then a one-time code by SMS) creates the chat session already verified; if that expires, Nova verifies again in the chat (document + date of birth + code), only as the logged-in customer. Before that, the agent only answers public questions (products, policies).
3. After the check, the agent looks up **only that customer's** data with tools (products, transactions, complaints) that take no customer id: the backend uses the verified session's (`backend/app/agent/account_tools.py`).
4. It tries to **solve the issue in this first contact**. If it can't, it **hands over to a human** (`backend/app/agent/handoff.py`): a case with its summary and open questions, plus the verified facts and the evidence from code, answered from the agent console (`/asesor`).
5. **Hooks** block forbidden actions; **guardrails** block access to other customers' data.

## Building blocks
| Part | Technology |
|---|---|
| Agent | LangGraph (steps and security rules) + LangChain (models, tools) |
| LLM | Claude on Amazon Bedrock (production); Hugging Face Inference Providers, free tier (local only) |
| Knowledge answers | RAG over products, policies, FAQs |
| Customer data for the agent | DynamoDB |
| Contact center model | Intent classifier (scikit-learn TF-IDF + logistic regression, run in plain Python in the Lambda) + the bank's FCR by reason from `latam_curated`. See `ml/README.md` |
| API | FastAPI |
| Hosting | CloudFront + S3 (frontend), Lambda function URL with streaming (API), DynamoDB (interactions). See `infra/app` |
| Infrastructure | Terraform |

## Data
```
organizers' bucket ──copy──▶ data-root (original CSV, never modified)
                                   │  Athena + dbt (data/dbt)
                                   ▼
                          hackaton-data/curated (clean Parquet: dim_*, fact_interaction, fact_transaction)
                                   │
                                   ▼
                          notebooks and models (ml/)
```
Main tables: `call_center_interactions`, `call_transcripts`, `satisfaction_surveys`, `service_agents`, `complaints`, `customers`.

## Security
- Identity checked before any personal data; every lookup limited to the verified customer.
- Production calls to the LLM only go through Bedrock; the app refuses to start otherwise.
- No personal identifiers in the cleaned tables; no data or secrets in the repo.
- Team access to AWS through personal IAM users (one access key each, deleted after the hackathon).

## Still to decide
- The single customer flow for the demo
- When to hand over to a human
