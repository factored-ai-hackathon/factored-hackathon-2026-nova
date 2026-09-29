# ---------------------------------------------------------------------------
# Data pipeline role: .github/workflows/data.yml builds the production data
# model (dbt --target prod -> latam_curated) on every merge to main, through
# GitHub OIDC (no AWS keys in GitHub). Least privilege: read the raw data,
# write only latam_curated, run queries only in the capped workgroup.
# The OIDC provider itself is created by infra/app.
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

locals {
  account_id   = data.aws_caller_identity.current.account_id
  glue_catalog = "arn:aws:glue:${var.region}:${local.account_id}:catalog"
  glue_raw     = "arn:aws:glue:${var.region}:${local.account_id}:database/${aws_glue_catalog_database.raw.name}"
  glue_curated = "arn:aws:glue:${var.region}:${local.account_id}:database/${aws_glue_catalog_database.curated.name}"
}

resource "aws_iam_role" "dbt" {
  name = "${var.bucket_prefix}-github-dbt"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:ref:refs/heads/main"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "dbt" {
  name = "dbt-prod"
  role = aws_iam_role.dbt.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "QueriesInTheCappedWorkgroup"
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution", "athena:StopQueryExecution", "athena:GetQueryExecution",
          "athena:GetQueryResults", "athena:BatchGetQueryExecution", "athena:GetWorkGroup",
        ]
        Resource = aws_athena_workgroup.hackathon.arn
      },
      {
        Sid      = "DefaultDataCatalog"
        Effect   = "Allow"
        Action   = ["athena:GetDataCatalog", "athena:ListDataCatalogs"]
        Resource = "*"
      },
      {
        Sid    = "ReadRawTables"
        Effect = "Allow"
        Action = [
          "glue:GetDatabase", "glue:GetDatabases", "glue:GetTable", "glue:GetTables",
          "glue:GetPartition", "glue:GetPartitions", "glue:BatchGetPartition",
        ]
        Resource = [local.glue_catalog, local.glue_raw, "arn:aws:glue:${var.region}:${local.account_id}:table/${aws_glue_catalog_database.raw.name}/*"]
      },
      {
        Sid    = "WriteCuratedTables"
        Effect = "Allow"
        Action = [
          "glue:GetDatabase", "glue:GetDatabases", "glue:GetTable", "glue:GetTables",
          "glue:CreateTable", "glue:UpdateTable", "glue:DeleteTable", "glue:BatchDeleteTable",
          "glue:GetTableVersions", "glue:DeleteTableVersion", "glue:BatchDeleteTableVersion",
          "glue:GetPartition", "glue:GetPartitions", "glue:BatchGetPartition",
          "glue:CreatePartition", "glue:BatchCreatePartition", "glue:UpdatePartition",
          "glue:DeletePartition", "glue:BatchDeletePartition",
        ]
        Resource = [local.glue_catalog, local.glue_curated, "arn:aws:glue:${var.region}:${local.account_id}:table/${aws_glue_catalog_database.curated.name}/*"]
      },
      {
        Sid      = "ListBuckets"
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:GetBucketLocation"]
        Resource = [aws_s3_bucket.data_root.arn, aws_s3_bucket.work.arn]
      },
      {
        # Original CSVs and the transcripts Parquet copy.
        Sid      = "ReadSourceData"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.data_root.arn}/*", "${aws_s3_bucket.work.arn}/converted/*"]
      },
      {
        Sid    = "WriteCuratedDataAndQueryResults"
        Effect = "Allow"
        Action = [
          "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
          "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts",
        ]
        Resource = [
          "${aws_s3_bucket.work.arn}/curated/${aws_glue_catalog_database.curated.name}/*",
          "${aws_s3_bucket.work.arn}/athena-results/*",
        ]
      },
    ]
  })
}
