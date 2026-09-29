# infra/app

Production hosting for the chat app (decision 19). Owner: Paul.

```
browser ──https──▶ CloudFront ─┬─ /*            ─▶ S3 (frontend build, private, OAC)
                               └─ /v1/*, /health ─▶ Lambda function URL (streaming)
                                                      FastAPI + Lambda Web Adapter, arm64
                                                      ├─▶ Bedrock (Claude Haiku 4.5)
                                                      └─▶ DynamoDB (chat interactions, TTL)
```

- One origin for the browser, so no CORS. CloudFront adds a secret `X-Origin-Verify` header and the API rejects requests without it, so the public function URL can't be used directly.
- Lambda can only be invoked through its URL (`lambda:InvokedViaFunctionUrl`).
- GitHub Actions deploys through OIDC (no AWS keys in GitHub). The role only works from `main` and can only update this app's code and web files.
- Terraform creates the infrastructure once; `.github/workflows/deploy.yml` ships new code on every push to `main`.

## First deploy (Paul, with admin-level credentials: it creates IAM roles)
```bash
cp infra/app/terraform.tfvars.example infra/app/terraform.tfvars
backend/scripts/build_lambda.sh                 # first Lambda package (needs uv)
terraform -chdir=infra/app init
terraform -chdir=infra/app plan -out=tfplan     # review, get approval
terraform -chdir=infra/app apply tfplan
terraform -chdir=infra/app output github_variables
```
Then:
1. Add each `github_variables` entry as a repository **variable** (Settings → Secrets and variables → Actions → Variables).
2. Run the **Deploy** workflow once (Actions → Deploy → Run workflow on `main`) to upload the frontend. Until then the site returns 403 (empty bucket).
3. Open `app_url`.

If `terraform apply` says the GitHub OIDC provider already exists, set `create_github_oidc_provider = false`.

If the deploy fails with `Not authorized to perform sts:AssumeRoleWithWebIdentity`, the role's trust policy doesn't match the token's `sub` claim. CloudTrail shows the `sub` GitHub sent (event `AssumeRoleWithWebIdentity`, field `userIdentity.userName`); set `github_repo` to its repository part. This organization's claims use immutable IDs (`owner@id/repo@id`).

## Cost (demo traffic)
| Resource | Cost |
|---|---|
| Lambda, CloudFront, DynamoDB on-demand, S3 | Free tier / cents |
| CloudWatch Logs (14-day retention) | Cents |
| Bedrock Claude Haiku 4.5 | $1 / $5 per million input / output tokens; the only cost that grows with use |

**Spend limits (decision 20):** the API stops calling Bedrock once the day's spend reaches `daily_budget_usd` ($5, about 2,000+ messages) and refuses a visitor after `rate_limit_per_hour` messages (30). Both answer `429` and Nova tells the customer. Change them in `terraform.tfvars` and apply. Replies are also capped by `LLM_MAX_TOKENS` (1024) and messages by 2,000 characters. `lambda_reserved_concurrency` can additionally cap parallel requests if the account's Lambda concurrency quota allows it.

## Known limits
- Sessions and conversation memory are in memory per Lambda instance. A new instance (cold start, parallel users) starts a new conversation; the frontend recovers from the `404` automatically. Moving sessions to DynamoDB fixes it.
- CloudFront waits up to 60 s for the API (`origin_read_timeout`), enough for a reply.
