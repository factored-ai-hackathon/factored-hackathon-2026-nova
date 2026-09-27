# Decisions

To change a decision, add a new row that replaces the old one. Don't edit old rows.

| # | Date | Decision | Why |
|---|---|---|---|
| 1 | 09-26 | One repo, one folder per area (`infra`, `docs`, `frontend`, `backend`, `ml`, `data`, `evals`) | One place for the team and the judges |
| 2 | 09-27 | Focus on the **contact center** (first contact resolution, agent performance, sentiment). Credit-eligibility agent dropped | The dataset is rich in contact center data; one flow done well |
| 3 | 09-27 | Data lake: S3 (`data-root` = original data, never modified; `hackaton-data` = our results) + Glue catalog + Athena | Costs cents; nothing to run or maintain |
| 4 | 09-27 | Clean and model data with **dbt SQL on Athena**, not Glue jobs | About 10–100x cheaper at our size; SQL is easier for everyone |
| 5 | 09-27 | Star schema with **`fact_interaction`** at the centre. FCR = resolved and no repeat contact on the same topic within 7 days | Standard, defensible metric |
| 6 | 09-26 | Keep original data untouched and keep nulls. Don't use the organizers' `data_backup_20260831` | It's a different version of the data with different IDs |
| 7 | 09-27 | No names, documents, contact details or addresses in the cleaned tables | Security first; the repo is public |
| 8 | 09-27 | Agent built with **LangGraph + LangChain** | Security rules enforced in code, not just in the prompt |
| 9 | 09-27 | **Bedrock** in production; **OpenRouter** free models only for local development, with test data only | Bedrock: no API keys, data stays in AWS. OpenRouter: $0 while building |
| 10 | 09-27 | Cost limits: budget alerts (set up manually in the AWS console), 10 GB cap per Athena query, no always-on services, train models on laptops | We pay for AWS |
| 11 | 09-27 | Terraform state kept on Paul's laptop for now | Only Paul changes infrastructure |
| 12 | 09-27 | ML starts with scikit-learn and simple baselines; add other libraries only if they prove better | Simple first, no extra installs |
| 13 | 09-27 | Team access through personal **IAM users with access keys** (group `hackaton-team`), created manually. Replaces the SSO plan | Quicker to set up for a 10-day project. One key per person, never shared; delete users and keys after Oct 16 |
| 14 | 09-27 | Terraform only creates stable infrastructure (buckets, Glue databases, Athena workgroup). All tables, raw and curated, are managed with dbt | The data team can change tables without Terraform or infrastructure access |
| 15 | 09-27 | `call_transcripts` is read from a Parquet copy (`data/scripts/convert_transcripts.py`), not the CSV | Every transcript has line breaks in its text; Athena split them into ~925k broken rows. The original CSV stays untouched |
| 16 | 09-27 | MVP chat uses **Hugging Face Inference Providers** (free tier, `openai/gpt-oss-20b` through the OpenAI-compatible router) for local development. Replaces OpenRouter there (row 9). Production stays Bedrock only: the app refuses to start with `APP_ENV=prod` and another provider. Only synthetic/test text is sent to HF | One client (`ChatOpenAI`) gives streaming and tool calling. The free tier is only $0.10/month, so tests and evals use a fake model; switch to Bedrock before full eval runs |
