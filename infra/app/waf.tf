# AWS WAF in front of CloudFront (decisions 43 and 49). Everything is refused at the edge, before it
# invokes (and bills) the Lambda. A CloudFront web ACL must live in us-east-1. Cost: ~$5/month for
# the ACL + $1/month per rule + $0.60 per million requests; the AWS managed rule groups used here
# have no extra charge and the whole ACL stays under the 1,500 WCU included.
#
# Order of evaluation (lowest priority first; the first terminating action wins):
#   0  admin-allow        the operators' own IPs (var.waf_admin_ips, only in terraform.tfvars) skip
#                         every rule below, so tests and evaluation runs are never rate limited.
#   1  ip-reputation      AWS list of IPs known for bots, scanners and attacks.
#   2  site-flood         per-IP ceiling on every path, pages included.
#   3  api-label          labels API requests (/v1/* and /health, the paths CloudFront sends to the
#                         Lambda) as fh26:api. Count only.
#   4-5 api-route-get/post label the API requests whose method AND path are in the allowlist (the
#                         routes the frontend calls) as fh26:route-ok. Count only.
#   6  api-unknown-route  any other API request: 404 blocked_route. Scanners, wrong methods,
#                         OPTIONS/PUT/DELETE, encoded or traversal paths never reach the app.
#   7  api-body-too-large API bodies over 16 KB (the largest real one is a 2,000-character message).
#   8  known-bad-inputs   AWS managed: Log4j/JNDI, Java deserialization, localhost host headers...
#   9  common-rules       AWS managed core rule set (XSS, LFI/RFI, SSRF to instance metadata, no
#                         user agent...), its own body size rule left to rule 7.
#   10-12 live/auth/demo-per-ip  tight per-IP limits on the public reads and the login.
#   13 api-per-ip         per-IP limit on the rest of the API (polled paths left out).
#   14 api-flood          per-IP ceiling on every API path, polled ones included.
#
# Switches: waf_block = false turns rules 2-7 and 10-14 into count only; waf_managed_rules_block =
# false does the same for 1, 8 and 9. Both show up in the WAF metrics either way.

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

  # The admin list may mix IPv4 and IPv6 CIDRs; WAF needs one IP set per version.
  waf_admin_ipv4 = [for c in var.waf_admin_ips : c if !strcontains(c, ":")]
  waf_admin_ipv6 = [for c in var.waf_admin_ips : c if strcontains(c, ":")]

  # API ids: session and message UUIDs, case ids (NB-XXXXXX), dataset customer ids.
  waf_id = "[A-Za-z0-9_-]{1,64}"

  # Every API route the frontend calls, by method (backend/app/api, frontend/src/api).
  # Anything else under /v1/ or /health is refused at the edge (rule 6).
  waf_get_routes = [
    "^/health$",
    "^/v1/metrics/live$",
    "^/v1/demo/scenarios$",
    "^/v1/demo/customers/${local.waf_id}$",
  ]
  waf_post_routes = [
    "^/v1/auth/(login|verify)$",
    "^/v1/accounts/overview$",
    "^/v1/(public/)?chat/sessions$",
    "^/v1/(public/)?chat/sessions/${local.waf_id}/messages$",
    "^/v1/chat/sessions/${local.waf_id}/handoff(/rating)?$",
    "^/v1/chat/sessions/${local.waf_id}/messages/${local.waf_id}/feedback$",
    "^/v1/agent/cases(/${local.waf_id}(/(take|reply|close))?)?$",
  ]

  # Per-IP rate limits on single paths or prefixes: rule name => [priority, match, path, limit].
  waf_path_limits = {
    live-per-ip = [10, "EXACTLY", "/v1/metrics/live", var.waf_live_limit]
    auth-per-ip = [11, "STARTS_WITH", "/v1/auth/", var.waf_auth_limit]
    demo-per-ip = [12, "STARTS_WITH", "/v1/demo/", var.waf_demo_limit]
  }

  waf_response_bodies = {
    rate_limited  = "rate_limited"
    blocked_route = "blocked_route"
    too_large     = "request_too_large"
  }

  # Labels added by the count-only rules (namespace fh26).
  waf_label_api      = "fh26:api"
  waf_label_route_ok = "fh26:route-ok"
}

resource "aws_wafv2_ip_set" "admin_v4" {
  provider           = aws.us_east_1
  name               = "${var.prefix}-admin-v4"
  description        = "Operators allowed past every WAF rule (from terraform.tfvars)"
  scope              = "CLOUDFRONT"
  ip_address_version = "IPV4"
  addresses          = local.waf_admin_ipv4
}

resource "aws_wafv2_ip_set" "admin_v6" {
  provider           = aws.us_east_1
  name               = "${var.prefix}-admin-v6"
  description        = "Operators allowed past every WAF rule (from terraform.tfvars)"
  scope              = "CLOUDFRONT"
  ip_address_version = "IPV6"
  addresses          = local.waf_admin_ipv6
}

resource "aws_wafv2_regex_pattern_set" "api_get" {
  provider    = aws.us_east_1
  name        = "${var.prefix}-api-get-routes"
  description = "API paths allowed with GET"
  scope       = "CLOUDFRONT"

  dynamic "regular_expression" {
    for_each = local.waf_get_routes
    content {
      regex_string = regular_expression.value
    }
  }
}

resource "aws_wafv2_regex_pattern_set" "api_post" {
  provider    = aws.us_east_1
  name        = "${var.prefix}-api-post-routes"
  description = "API paths allowed with POST"
  scope       = "CLOUDFRONT"

  dynamic "regular_expression" {
    for_each = local.waf_post_routes
    content {
      regex_string = regular_expression.value
    }
  }
}

resource "aws_wafv2_web_acl" "app" {
  provider    = aws.us_east_1
  name        = "${var.prefix}-app"
  description = "Edge protection for the demo: route allowlist, managed rules and per-IP rate limits"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  # The bodies the API itself would send, so the app shows its usual messages. Only when the rules
  # block: in count mode nothing references them.
  dynamic "custom_response_body" {
    for_each = { for k, v in local.waf_response_bodies : k => v if var.waf_block }
    content {
      key          = custom_response_body.key
      content      = jsonencode({ detail = custom_response_body.value })
      content_type = "APPLICATION_JSON"
    }
  }

  # 0. Operators: allow and stop. Only exists when terraform.tfvars lists an address.
  dynamic "rule" {
    for_each = length(var.waf_admin_ips) > 0 ? [1] : []
    content {
      name     = "admin-allow"
      priority = 0

      action {
        allow {}
      }

      statement {
        or_statement {
          statement {
            ip_set_reference_statement {
              arn = aws_wafv2_ip_set.admin_v4.arn
            }
          }
          statement {
            ip_set_reference_statement {
              arn = aws_wafv2_ip_set.admin_v6.arn
            }
          }
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = "${var.prefix}-admin-allow"
        sampled_requests_enabled   = true
      }
    }
  }

  # 1. AWS managed list of IPs with a bad reputation (bots, scanners, known attackers).
  rule {
    name     = "ip-reputation"
    priority = 1

    override_action {
      dynamic "none" {
        for_each = var.waf_managed_rules_block ? [1] : []
        content {}
      }
      dynamic "count" {
        for_each = var.waf_managed_rules_block ? [] : [1]
        content {}
      }
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesAmazonIpReputationList"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.prefix}-ip-reputation"
      sampled_requests_enabled   = true
    }
  }

  # 2. Every path, pages and assets included: a ceiling no visitor reaches (a page load is ~20
  # requests), against floods on the static site.
  rule {
    name     = "site-flood"
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
        limit                 = var.waf_site_limit
        evaluation_window_sec = 300
        aggregate_key_type    = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.prefix}-site-flood"
      sampled_requests_enabled   = true
    }
  }

  # 3. Label the requests CloudFront sends to the Lambda (its behaviors: /v1/* and /health).
  rule {
    name     = "api-label"
    priority = 3

    action {
      count {}
    }

    rule_label {
      name = local.waf_label_api
    }

    statement {
      or_statement {
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
          byte_match_statement {
            search_string         = "/health"
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

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.prefix}-api-label"
      sampled_requests_enabled   = false
    }
  }

  # 4-5. Label the allowed (method, path) pairs. The regexes are anchored, so a path with an
  # encoded or traversal segment, a trailing slash or an extra part does not match.
  dynamic "rule" {
    for_each = {
      api-route-get  = { priority = 4, method = "GET", set = aws_wafv2_regex_pattern_set.api_get.arn }
      api-route-post = { priority = 5, method = "POST", set = aws_wafv2_regex_pattern_set.api_post.arn }
    }
    content {
      name     = rule.key
      priority = rule.value.priority

      action {
        count {}
      }

      rule_label {
        name = local.waf_label_route_ok
      }

      statement {
        and_statement {
          statement {
            byte_match_statement {
              search_string         = rule.value.method
              positional_constraint = "EXACTLY"
              field_to_match {
                method {}
              }
              text_transformation {
                priority = 0
                type     = "NONE"
              }
            }
          }
          statement {
            regex_pattern_set_reference_statement {
              arn = rule.value.set
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
        metric_name                = "${var.prefix}-${rule.key}"
        sampled_requests_enabled   = false
      }
    }
  }

  # 6. An API request that is not an allowed route: refused before the Lambda.
  rule {
    name     = "api-unknown-route"
    priority = 6

    action {
      dynamic "block" {
        for_each = local.waf_action == "block" ? [1] : []
        content {
          custom_response {
            response_code            = 404
            custom_response_body_key = "blocked_route"
          }
        }
      }
      dynamic "count" {
        for_each = local.waf_action == "count" ? [1] : []
        content {}
      }
    }

    statement {
      and_statement {
        statement {
          label_match_statement {
            scope = "LABEL"
            key   = local.waf_label_api
          }
        }
        statement {
          not_statement {
            statement {
              label_match_statement {
                scope = "LABEL"
                key   = local.waf_label_route_ok
              }
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.prefix}-api-unknown-route"
      sampled_requests_enabled   = true
    }
  }

  # 7. API bodies over 16 KB. CloudFront web ACLs inspect the first 16 KB of a body; a larger one is
  # "oversize" and MATCH makes it count as too large.
  rule {
    name     = "api-body-too-large"
    priority = 7

    action {
      dynamic "block" {
        for_each = local.waf_action == "block" ? [1] : []
        content {
          custom_response {
            response_code            = 413
            custom_response_body_key = "too_large"
          }
        }
      }
      dynamic "count" {
        for_each = local.waf_action == "count" ? [1] : []
        content {}
      }
    }

    statement {
      and_statement {
        statement {
          label_match_statement {
            scope = "LABEL"
            key   = local.waf_label_api
          }
        }
        statement {
          size_constraint_statement {
            comparison_operator = "GT"
            size                = 16384
            field_to_match {
              body {
                oversize_handling = "MATCH"
              }
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
      metric_name                = "${var.prefix}-api-body-too-large"
      sampled_requests_enabled   = true
    }
  }

  # 8-9. AWS managed signatures, on API requests only (the pages are static files).
  dynamic "rule" {
    for_each = {
      known-bad-inputs = { priority = 8, group = "AWSManagedRulesKnownBadInputsRuleSet", count_rules = [] }
      # Its 8 KB body rule would refuse a long message that rule 7 accepts: counted, not blocked.
      common-rules = { priority = 9, group = "AWSManagedRulesCommonRuleSet", count_rules = ["SizeRestrictions_BODY"] }
    }
    content {
      name     = rule.key
      priority = rule.value.priority

      override_action {
        dynamic "none" {
          for_each = var.waf_managed_rules_block ? [1] : []
          content {}
        }
        dynamic "count" {
          for_each = var.waf_managed_rules_block ? [] : [1]
          content {}
        }
      }

      statement {
        managed_rule_group_statement {
          vendor_name = "AWS"
          name        = rule.value.group

          dynamic "rule_action_override" {
            for_each = rule.value.count_rules
            content {
              name = rule_action_override.value
              action_to_use {
                count {}
              }
            }
          }

          scope_down_statement {
            label_match_statement {
              scope = "LABEL"
              key   = local.waf_label_api
            }
          }
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = "${var.prefix}-${rule.key}"
        sampled_requests_enabled   = true
      }
    }
  }

  # 10-12. Tight per-IP limits: the live metrics read (the /models page polls it once a minute), the
  # login (against guessing) and the demo lookups (against walking the customer directory).
  dynamic "rule" {
    for_each = local.waf_path_limits
    content {
      name     = rule.key
      priority = rule.value[0]

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
          limit                 = rule.value[3]
          evaluation_window_sec = 300
          aggregate_key_type    = "IP"

          scope_down_statement {
            byte_match_statement {
              search_string         = rule.value[2]
              positional_constraint = rule.value[1]
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
        metric_name                = "${var.prefix}-${rule.key}"
        sampled_requests_enabled   = true
      }
    }
  }

  # 13. The rest of the API: at most var.waf_api_limit requests per IP in 5 minutes. Left out: the
  # agent console (/v1/agent/*, polls every 4 s), the customer's handoff poll (.../handoff, every
  # 3 s while a case is open) and /v1/metrics/live (rule 10); rule 14 still covers them.
  rule {
    name     = "api-per-ip"
    priority = 13

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

        # NOT (agent OR handoff OR live), written as NOT agent AND NOT handoff AND NOT live:
        # the provider allows only one level of nesting inside the scope-down AND.
        scope_down_statement {
          and_statement {
            statement {
              label_match_statement {
                scope = "LABEL"
                key   = local.waf_label_api
              }
            }
            statement {
              not_statement {
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
              }
            }
            statement {
              not_statement {
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
              }
            }
            statement {
              not_statement {
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

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.prefix}-api-per-ip"
      sampled_requests_enabled   = true
    }
  }

  # 14. Every API path, the polled ones included: a ceiling no real page reaches (/console open for
  # 5 minutes is ~75-150 requests), against floods.
  rule {
    name     = "api-flood"
    priority = 14

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
          label_match_statement {
            scope = "LABEL"
            key   = local.waf_label_api
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
