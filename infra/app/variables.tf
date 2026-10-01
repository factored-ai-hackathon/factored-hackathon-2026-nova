variable "region" {
  description = "AWS region for everything except CloudFront (global). Same region as the data lake."
  type        = string
  default     = "us-east-2"
}

variable "aws_profile" {
  description = "Local AWS CLI profile (e.g. hackathon). Null uses the default credential chain."
  type        = string
  default     = null
}

variable "prefix" {
  description = "Short prefix for resource names (fh26 = Factored Hackathon 2026). Bucket names are global."
  type        = string
  default     = "fh26"
}

variable "bedrock_model_id" {
  description = "Bedrock inference profile the API calls. Must match the app default (decision 17)."
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "embedding_model_id" {
  description = "Bedrock model that embeds the question for the knowledge search (decision 32)."
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "bedrock_regions" {
  description = "Regions the US cross-Region inference profile can route to."
  type        = list(string)
  default     = ["us-east-1", "us-east-2", "us-west-2"]
}

variable "lambda_package_path" {
  description = "Zip built by backend/scripts/build_lambda.sh. Only used on the first apply; CI deploys later versions."
  type        = string
  default     = "../../backend/build/lambda.zip"
}

variable "lambda_memory_mb" {
  description = "Lambda memory. More memory also means more CPU, so faster cold starts."
  type        = number
  default     = 1024
}

variable "lambda_timeout_seconds" {
  description = "Max time per request (a streamed reply). CloudFront waits up to 60 s for the origin."
  type        = number
  default     = 60
}

variable "lambda_reserved_concurrency" {
  description = "Caps concurrent Lambda instances, so Bedrock spend has a ceiling. Null = no cap. Needs enough unreserved account concurrency (new accounts may only have 10)."
  type        = number
  default     = null
}

variable "lwa_layer_version" {
  description = "Version of the public Lambda Web Adapter layer (LambdaAdapterLayerArm64)."
  type        = number
  default     = 30
}

variable "daily_budget_usd" {
  description = "Max Bedrock spend per day (UTC) for the public chat. Once reached, the API answers 429 until the next day."
  type        = number
  default     = 5
}

variable "rate_limit_per_hour" {
  description = "Max chat messages per visitor (IP) per hour."
  type        = number
  default     = 30
}

variable "session_ttl_hours" {
  description = "Hours without activity before a chat session and its history expire."
  type        = number
  default     = 24
}

variable "interactions_ttl_days" {
  description = "Days before a recorded chat turn is deleted by DynamoDB TTL."
  type        = number
  default     = 30
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the API."
  type        = number
  default     = 14
}

variable "cloudfront_price_class" {
  description = "PriceClass_All includes South American edges (users in LATAM). Demo traffic stays in the free tier."
  type        = string
  default     = "PriceClass_All"
}

variable "github_repo" {
  description = "Repository allowed to deploy (from the main branch only), as it appears in the GitHub OIDC `sub` claim. This organization uses immutable IDs: owner@owner_id/repo@repo_id (public GitHub IDs, not secrets). They protect against a deleted and re-created repo with the same name."
  type        = string
  default     = "factored-ai-hackathon@332501550/factored-hackathon-2026@1382401057"
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub Actions OIDC provider. Set false if the account already has one."
  type        = bool
  default     = true
}
