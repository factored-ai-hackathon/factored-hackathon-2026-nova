# Glue Data Catalog databases (free under 1M objects) so Athena can query the data.
#
# Only the databases live in Terraform. Tables are managed by the data team with
# dbt (data/dbt), so they can change them without touching infrastructure:
#   latam_raw      raw tables over the original CSV in data-root
#                  (dbt run-operation create_raw_tables)
#   latam_curated  cleaned Parquet tables built by dbt build

resource "aws_glue_catalog_database" "raw" {
  name        = "latam_raw"
  description = "LATAM Bank dataset as delivered (gzipped CSV, all columns STRING). Tables created by dbt."
}

resource "aws_glue_catalog_database" "curated" {
  name         = "latam_curated"
  description  = "Cleaned, typed Parquet tables built by dbt."
  location_uri = "s3://${aws_s3_bucket.work.bucket}/curated/"
}
