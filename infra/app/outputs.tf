output "app_url" {
  description = "Public link to the demo."
  value       = "https://${aws_cloudfront_distribution.app.domain_name}"
}

output "lambda_function_name" {
  value = aws_lambda_function.api.function_name
}

output "sessions_table" {
  value = aws_dynamodb_table.sessions.name
}

output "interactions_table" {
  value = aws_dynamodb_table.interactions.name
}

# Set these as repository variables (Settings > Secrets and variables > Actions > Variables).
# None is a secret: the role can only be assumed from this repo's main branch.
output "github_variables" {
  value = {
    AWS_REGION                 = var.region
    AWS_DEPLOY_ROLE_ARN        = aws_iam_role.deploy.arn
    ARTIFACTS_BUCKET           = aws_s3_bucket.artifacts.id
    LAMBDA_FUNCTION_NAME       = aws_lambda_function.api.function_name
    WEB_BUCKET                 = aws_s3_bucket.web.id
    CLOUDFRONT_DISTRIBUTION_ID = aws_cloudfront_distribution.app.id
    APP_URL                    = "https://${aws_cloudfront_distribution.app.domain_name}"
  }
}

output "demo_customers_table" {
  value = aws_dynamodb_table.demo_customers.name
}
