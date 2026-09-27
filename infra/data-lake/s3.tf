locals {
  # Bucket names are global across all AWS accounts; the short project prefix
  # keeps them unique.
  data_root_bucket = "${var.bucket_prefix}-data-root"
  work_bucket      = "${var.bucket_prefix}-hackaton-data"
}

# ---------------------------------------------------------------------------
# data-root: pristine copy of the organizers' dataset (gzipped CSV).
# Read-only by convention and by policy: object deletes are denied.
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "data_root" {
  bucket = local.data_root_bucket
}

# ---------------------------------------------------------------------------
# hackaton-data: working bucket.
#   curated/        Parquet written by Athena CTAS (cleaned, typed)
#   features/       feature tables for modeling
#   models/         trained model artifacts
#   athena-results/ query results (auto-expired)
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "work" {
  bucket = local.work_bucket
}

locals {
  buckets = {
    data_root = aws_s3_bucket.data_root
    work      = aws_s3_bucket.work
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = local.buckets

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  for_each = local.buckets

  bucket = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# SSE-S3 is free; a customer-managed KMS key would add $1/month per key.
resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = local.buckets

  bucket = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data_root" {
  bucket = aws_s3_bucket.data_root.id

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "work" {
  bucket = aws_s3_bucket.work.id

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  rule {
    id     = "expire-athena-results"
    status = "Enabled"
    filter {
      prefix = "athena-results/"
    }
    expiration {
      days = 7
    }
  }
}

data "aws_iam_policy_document" "data_root" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.data_root.arn, "${aws_s3_bucket.data_root.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  # Keeps the original data immutable. To delete on purpose, remove this
  # statement with a reviewed terraform apply first.
  statement {
    sid       = "DenyDeletingOriginalData"
    effect    = "Deny"
    actions   = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = ["${aws_s3_bucket.data_root.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
}

data "aws_iam_policy_document" "work" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.work.arn, "${aws_s3_bucket.work.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "data_root" {
  bucket     = aws_s3_bucket.data_root.id
  policy     = data.aws_iam_policy_document.data_root.json
  depends_on = [aws_s3_bucket_public_access_block.this]
}

resource "aws_s3_bucket_policy" "work" {
  bucket     = aws_s3_bucket.work.id
  policy     = data.aws_iam_policy_document.work.json
  depends_on = [aws_s3_bucket_public_access_block.this]
}
