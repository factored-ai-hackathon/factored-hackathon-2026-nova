# ---------------------------------------------------------------------------
# Chat API: FastAPI on Lambda (arm64) behind Lambda Web Adapter, with response
# streaming through a function URL, so SSE replies stream token by token.
# ---------------------------------------------------------------------------

# Deployment packages. Too big (> 50 MB zipped) to upload straight to Lambda.
resource "aws_s3_bucket" "artifacts" {
  bucket = "${var.prefix}-hackaton-artifacts"
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# First package only. After that, the deploy workflow uploads new code to the same key.
resource "aws_s3_object" "lambda_package" {
  bucket = aws_s3_bucket.artifacts.id
  key    = local.lambda_s3_key
  source = var.lambda_package_path

  lifecycle {
    ignore_changes = [source, etag]
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "api" {
  name = "${local.function_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "api" {
  name = "chat-api"
  role = aws_iam_role.api.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.api.arn}:*"
      },
      {
        # The cross-Region inference profile, plus the model in each Region it routes to.
        Sid    = "InvokeClaude"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = concat(
          ["arn:aws:bedrock:${var.region}:${local.account_id}:inference-profile/${var.bedrock_model_id}"],
          [for r in var.bedrock_regions : "arn:aws:bedrock:${r}::foundation-model/${trimprefix(var.bedrock_model_id, "us.")}"],
        )
      },
      {
        Sid      = "RecordInteractions"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.interactions.arn
      },
    ]
  })
}

resource "aws_lambda_function" "api" {
  function_name = local.function_name
  role          = aws_iam_role.api.arn
  runtime       = "python3.12"
  architectures = ["arm64"]
  handler       = "run.sh"
  memory_size   = var.lambda_memory_mb
  timeout       = var.lambda_timeout_seconds

  s3_bucket = aws_s3_bucket.artifacts.id
  s3_key    = aws_s3_object.lambda_package.key

  reserved_concurrent_executions = var.lambda_reserved_concurrency

  layers = [
    "arn:aws:lambda:${var.region}:753240598075:layer:LambdaAdapterLayerArm64:${var.lwa_layer_version}",
  ]

  environment {
    variables = {
      # Lambda Web Adapter
      AWS_LAMBDA_EXEC_WRAPPER      = "/opt/bootstrap"
      AWS_LWA_INVOKE_MODE          = "response_stream"
      AWS_LWA_READINESS_CHECK_PATH = "/health"
      PORT                         = "8000"
      # App (backend/app/config.py). AWS_REGION is set by Lambda.
      APP_ENV               = "prod"
      LLM_PROVIDER          = "bedrock"
      BEDROCK_MODEL_ID      = var.bedrock_model_id
      INTERACTIONS_STORE    = "dynamodb"
      INTERACTIONS_TABLE    = aws_dynamodb_table.interactions.name
      INTERACTIONS_TTL_DAYS = tostring(var.interactions_ttl_days)
      ORIGIN_VERIFY_SECRET  = random_password.origin_verify.result
    }
  }

  depends_on = [aws_cloudwatch_log_group.api, aws_iam_role_policy.api]

  lifecycle {
    # The deploy workflow updates the code; Terraform only creates the function.
    ignore_changes = [s3_key, s3_object_version, source_code_hash]
  }
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE" # CloudFront + X-Origin-Verify secret guard it (see main.tf)
  invoke_mode        = "RESPONSE_STREAM"
}

# Public function URLs need both statements (since Oct 2025). InvokedViaFunctionUrl keeps
# lambda:InvokeFunction limited to URL calls.
resource "aws_lambda_permission" "url_public" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "*"
  function_url_auth_type = "NONE"

  # One policy change at a time: parallel AddPermission calls on the same function conflict.
  depends_on = [aws_lambda_permission.url_invoke]
}

resource "aws_lambda_permission" "url_invoke" {
  statement_id             = "FunctionURLInvokeAllowPublicAccess"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api.function_name
  principal                = "*"
  invoked_via_function_url = true
}
