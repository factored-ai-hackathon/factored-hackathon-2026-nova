resource "aws_athena_workgroup" "hackathon" {
  name          = "hackathon"
  force_destroy = false

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = false
    bytes_scanned_cutoff_per_query     = var.athena_scan_limit_gb * 1024 * 1024 * 1024

    result_configuration {
      output_location = "s3://${aws_s3_bucket.work.bucket}/athena-results/"
      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
