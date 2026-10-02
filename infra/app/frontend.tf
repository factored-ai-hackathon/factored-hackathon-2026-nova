# ---------------------------------------------------------------------------
# Frontend on a private S3 bucket behind CloudFront. CloudFront also routes
# /v1/* and /health to the API, so the browser sees one origin (no CORS).
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "web" {
  bucket = "${var.prefix}-hackaton-web"
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = aws_s3_bucket.web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "web" {
  bucket = aws_s3_bucket.web.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${var.prefix}-web"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.web.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "CloudFrontReadOnly"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.web.arn}/*"
      Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.app.arn } }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.web]
}

# React Router paths (/dashboard, /agent) have no file behind them: serve index.html.
# Only on the S3 behavior, so API 404s (e.g. unknown session) reach the browser as 404s.
resource "aws_cloudfront_function" "spa_rewrite" {
  name    = "${var.prefix}-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = <<-JS
    function handler(event) {
      var request = event.request;
      if (!request.uri.includes('.')) {
        request.uri = '/index.html';
      }
      return request;
    }
  JS
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

# Only what the API needs. Not Host: the function URL must see its own host name.
# CloudFront-Viewer-Address is the visitor's IP, set by CloudFront (visitors can't fake it),
# used for the per-visitor rate limit.
resource "aws_cloudfront_origin_request_policy" "api" {
  name    = "${var.prefix}-chat-api"
  comment = "Chat API: content headers and the viewer IP"

  cookies_config {
    cookie_behavior = "none"
  }

  headers_config {
    header_behavior = "whitelist"
    headers {
      items = ["Accept", "Content-Type", "CloudFront-Viewer-Address"]
    }
  }

  query_strings_config {
    query_string_behavior = "all"
  }
}

locals {
  web_origin_id = "web-s3"
  api_origin_id = "chat-api"
  api_domain    = trimsuffix(trimprefix(aws_lambda_function_url.api.function_url, "https://"), "/")
}

resource "aws_cloudfront_distribution" "app" {
  enabled             = true
  comment             = "${var.prefix} chat app"
  default_root_object = "index.html"
  price_class         = var.cloudfront_price_class
  http_version        = "http2and3"
  is_ipv6_enabled     = true
  web_acl_id          = aws_wafv2_web_acl.app.arn # per-IP rate limits (waf.tf)

  origin {
    origin_id                = local.web_origin_id
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  origin {
    origin_id   = local.api_origin_id
    domain_name = local.api_domain

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      origin_read_timeout    = 60 # max without a quota increase
    }

    custom_header {
      name  = "X-Origin-Verify"
      value = random_password.origin_verify.result
    }
  }

  default_cache_behavior {
    target_origin_id       = local.web_origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
    compress               = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_rewrite.arn
    }
  }

  dynamic "ordered_cache_behavior" {
    for_each = ["/v1/*", "/health"]
    content {
      path_pattern             = ordered_cache_behavior.value
      target_origin_id         = local.api_origin_id
      viewer_protocol_policy   = "https-only"
      allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods           = ["GET", "HEAD"]
      cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
      origin_request_policy_id = aws_cloudfront_origin_request_policy.api.id
      compress                 = false # keep the SSE stream flowing token by token
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
