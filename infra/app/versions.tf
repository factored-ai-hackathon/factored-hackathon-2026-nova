terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # 6.x: aws_lambda_permission.invoked_via_function_url
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project   = "factored-hackathon-2026"
      Component = "app"
      ManagedBy = "terraform"
    }
  }
}
