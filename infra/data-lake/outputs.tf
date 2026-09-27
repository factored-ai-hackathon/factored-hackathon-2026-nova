output "data_root_bucket" {
  description = "Bucket with the original dataset (gzipped CSV)."
  value       = aws_s3_bucket.data_root.bucket
}

output "work_bucket" {
  description = "Working bucket: curated/, features/, models/, athena-results/."
  value       = aws_s3_bucket.work.bucket
}

output "athena_workgroup" {
  value = aws_athena_workgroup.hackathon.name
}

output "glue_databases" {
  value = {
    raw     = aws_glue_catalog_database.raw.name
    curated = aws_glue_catalog_database.curated.name
  }
}
