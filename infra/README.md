# infra

Infrastructure as code (Terraform). Owners: Paul

- `data-lake/`: S3 buckets (`data-root`, `hackaton-data`), Glue databases (`latam_raw`, `latam_curated`), Athena workgroup. Tables are not in Terraform: the data team manages them with dbt (`data/dbt`). (Budget alerts and team access via the `hackaton-team` group are set up manually in the console, not in Terraform.)

- `app/`: production hosting for the chat app: CloudFront + S3 (frontend), Lambda with streaming (API), DynamoDB (interactions), GitHub OIDC deploy role. See [app/README.md](app/README.md).

Always run `terraform plan` and get approval before `apply`. State and `*.tfvars` are gitignored.
