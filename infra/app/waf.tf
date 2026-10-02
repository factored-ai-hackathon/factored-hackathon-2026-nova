# AWS WAF in front of CloudFront (decision 43): per-IP rate limits on the API, enforced at the
# edge, so a flood or an endpoint scan is refused before it invokes (and bills) the Lambda.
# A CloudFront web ACL must live in us-east-1. ~$5/month for the ACL + $1/month per rule +
# $0.60 per million requests checked.
#
# Rollout: apply with waf_block = false (rules only count, visible in the WAF metrics), check that
# the demo pages don't trip them, then apply again with waf_block = true.

provider "aws" {
  alias   = "us_east_1"
  region  = "us-east-1"
  profile = var.aws_profile

  default_tags {
    tags = {
      Project   = "factored-hackathon-2026"
      Component = "app"
      ManagedBy = "terraform"
    }
  }
}

locals {
  waf_action = var.waf_block ? "block" : "count"
}

resource "aws_wafv2_web_acl" "app" {
  provider    = aws.us_east_1
  name        = "${var.prefix}-app"
  description = "Per-IP rate limits on the chat API"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  # The same body the API sends for its own limit, so the app shows its usual message.
  custom_response_body {
    key          = "rate_limited"
    content      = jsonencode({ detail = "rate_limited" })
    content_type = "APPLICATION_JSON"
  }

  # The user-facing API: at most var.waf_api_limit requests per IP in 5 minutes. Left out: the
  # agent console (/v1/agent/*, polls every 4 s), the customer's handoff poll (.../handoff, every
  # 3 s while a case is open) and /v1/metrics/live, which the flood rule below still covers.
  rule {
    name     = "api-per-ip"
    priority = 1

    action {
      dynamic "block" {
        for_each = local.waf_action == "block" ? [1] : []
        content {
          custom_response {
            response_code            = 429
            custom_response_body_key = "rate_limited"
          }
        }
      }
      dynamic "count" {
        for_each = local.waf_action == "count" ? [1] : []
        content {}
      }
    }

    statement {
      rate_based_statement {
        limit                 = var.waf_api_limit
        evaluation_window_sec = 300
        aggregate_key_type    = "IP"

        scope_down_statement {
          and_statement {
            statement {
              byte_match_statement {
                search_string         = "/v1/"
                positional_constraint = "STARTS_WITH"
                field_to_match {
                  uri_path {}
                }
                text_transformation {
                  priority = 0
                  type     = "NONE"
                }
              }
            }
            statement {
              not_statement {
                statement {
                  or_statement {
                    statement {
                      byte_match_statement {
                        search_string         = "/v1/agent/"
                        positional_constraint = "STARTS_WITH"
                        field_to_match {
                          uri_path {}
                        }
                        text_transformation {
                          priority = 0
                          type     = "NONE"
                        }
                      }
                    }
                    statement {
                      byte_match_statement {
                        search_string         = "/handoff"
                        positional_constraint = "ENDS_WITH"
                        field_to_match {
                          uri_path {}
                        }
                        text_transformation {
                          priority = 0
                          type     = "NONE"
                        }
                      }
                    }
                    statement {
                      byte_match_statement {
                        search_string         = "/v1/metrics/live"
                        positional_constraint = "EXACTLY"
                        field_to_match {
                          uri_path {}
                        }
                        text_transformation {
                          priority = 0
                          type     = "NONE"
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.prefix}-api-per-ip"
      sampled_requests_enabled   = true
    }
  }

  # Every API path, the polled ones included: a ceiling no real page reaches (/asesor open for
  # 5 minutes is ~75-150 requests), against floods.
  rule {
    name     = "api-flood"
    priority = 2

    action {
      dynamic "block" {
        for_each = local.waf_action == "block" ? [1] : []
        content {
          custom_response {
            response_code            = 429
            custom_response_body_key = "rate_limited"
          }
        }
      }
      dynamic "count" {
        for_each = local.waf_action == "count" ? [1] : []
        content {}
      }
    }

    statement {
      rate_based_statement {
        limit                 = var.waf_flood_limit
        evaluation_window_sec = 300
        aggregate_key_type    = "IP"

        scope_down_statement {
          byte_match_statement {
            search_string         = "/v1/"
            positional_constraint = "STARTS_WITH"
            field_to_match {
              uri_path {}
            }
            text_transformation {
              priority = 0
              type     = "NONE"
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.prefix}-api-flood"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.prefix}-app"
    sampled_requests_enabled   = true
  }
}
