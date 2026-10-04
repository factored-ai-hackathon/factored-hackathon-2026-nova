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

variable "github_repos" {
  description = "Repositories allowed to deploy (from the main branch only), as they appear in the GitHub OIDC `sub` claim. This organization uses immutable IDs: owner@owner_id/repo@repo_id (public GitHub IDs, not secrets). They protect against a deleted and re-created repo with the same name. The repo NAME is part of the claim, so renaming the repository changes it: the trust accepts a list (during the Oct 2026 rename it held the old and the new name; the old one was removed once a Deploy and a Data pipeline run had passed with the new name). Replaces the former single-string `github_repo` variable: a leftover `github_repo` line in terraform.tfvars is ignored with a warning, move it into this list."
  type        = list(string)
  default = [
    "factored-ai-hackathon@332501550/factored-hackathon-2026-nova@1382401057",
  ]
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub Actions OIDC provider. Set false if the account already has one."
  type        = bool
  default     = true
}

variable "waf_api_limit" {
  description = "Max API requests per IP in 5 minutes (WAF, decision 43). The agent console, the handoff poll and /v1/metrics/live are left out of it."
  type        = number
  default     = 100
}

variable "waf_flood_limit" {
  description = "Max requests per IP in 5 minutes on every API path, polled ones included (WAF)."
  type        = number
  default     = 600
}

variable "waf_site_limit" {
  description = "Max requests per IP in 5 minutes on every path, pages and assets included (WAF, decision 49). A page load is ~20 requests."
  type        = number
  default     = 3000
}

variable "waf_live_limit" {
  description = "Max GET /v1/metrics/live per IP in 5 minutes (WAF, decision 49). The /models page polls it once a minute."
  type        = number
  default     = 30
}

variable "waf_auth_limit" {
  description = "Max /v1/auth/* requests per IP in 5 minutes (WAF, decision 49). A login is 2 requests; judges may share one NAT."
  type        = number
  default     = 30
}

variable "waf_demo_limit" {
  description = "Max /v1/demo/* requests per IP in 5 minutes (WAF, decision 49): the demo panel's scenarios and customer lookups."
  type        = number
  default     = 60
}

variable "waf_admin_ips" {
  description = "Operators' public IPs as CIDRs (IPv4 /32, IPv6 /128 or /64) that skip every WAF rule, for tests and evaluation runs. Set it ONLY in terraform.tfvars (gitignored), never in the repo. Empty = no bypass rule."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for c in var.waf_admin_ips : can(cidrhost(c, 0))])
    error_message = "Each entry must be a CIDR, e.g. 203.0.113.10/32 or 2001:db8::/64."
  }
}

variable "waf_block" {
  description = "true (default): the custom WAF rules block (429 rate limits, 404 unknown routes, 413 large bodies); false: they only count, visible in the WAF metrics."
  type        = bool
  default     = true
}

variable "waf_managed_rules_block" {
  description = "true (default): the AWS managed rule groups (IP reputation, known bad inputs, core rule set) block with a 403; false: they only count. Use false if the dry run shows a false positive."
  type        = bool
  default     = true
}
