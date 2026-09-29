variable "region" {
  description = "AWS region for the buckets, Glue catalog and Athena. Same region as the organizers' bucket."
  type        = string
  default     = "us-east-2"
}

variable "bucket_prefix" {
  description = "Short prefix that makes the bucket names globally unique (fh26 = Factored Hackathon 2026)."
  type        = string
  default     = "fh26"
}

variable "aws_profile" {
  description = "Local AWS CLI profile (e.g. hackathon). Null uses the default credential chain."
  type        = string
  default     = null
}

variable "athena_scan_limit_gb" {
  description = "Max data scanned per Athena query. Protects against runaway costs ($5 per TB scanned)."
  type        = number
  default     = 10
}

variable "github_repo" {
  description = "Repository allowed to build the production data model (main branch only), as it appears in the GitHub OIDC `sub` claim (this organization uses immutable IDs: owner@id/repo@id, public GitHub IDs)."
  type        = string
  default     = "factored-ai-hackathon@332501550/factored-hackathon-2026@1382401057"
}
