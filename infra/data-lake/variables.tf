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

variable "github_repos" {
  description = "Repositories allowed to build the production data model (from the main branch only), as they appear in the GitHub OIDC `sub` claim. This organization uses immutable IDs: owner@owner_id/repo@repo_id (public GitHub IDs, not secrets). They protect against a deleted and re-created repo with the same name. The repo NAME is part of the claim, so renaming the repository changes it: the trust accepts a list (during the Oct 2026 rename it held the old and the new name; the old one was removed once a Deploy and a Data pipeline run had passed with the new name). Replaces the former single-string `github_repo` variable: a leftover `github_repo` line in terraform.tfvars is ignored with a warning, move it into this list."
  type        = list(string)
  default = [
    "factored-ai-hackathon@332501550/factored-hackathon-2026-nova@1382401057",
  ]
}
