data "aws_caller_identity" "current" {}

locals {
  account_id    = data.aws_caller_identity.current.account_id
  function_name = "${var.prefix}-chat-api"
  lambda_s3_key = "backend/lambda.zip"
}

# Shared by CloudFront (sends it) and the API (checks it): the public function URL only
# answers requests that came through CloudFront. Lives in the local state only.
resource "random_password" "origin_verify" {
  length  = 40
  special = false
}
