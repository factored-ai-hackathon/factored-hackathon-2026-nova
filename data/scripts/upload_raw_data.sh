#!/usr/bin/env bash
# Upload the gzipped LATAM Bank dataset to the data-root bucket, one folder per
# table so each Athena table has its own S3 location:
#   <table>/<table>.csv.gz                                    dimension tables
#   <table>/year=YYYY/month=MM/day=DD/<table>_YYYYMMDD.csv.gz fact tables
#
# Usage: scripts/upload_raw_data.sh <local data_gz dir> <data-root bucket name>
# Run with your own team profile (AWS_PROFILE=hackathon), not the organizers' keys.
set -euo pipefail

src="${1:?usage: $0 <local data_gz dir> <bucket>}"
bucket="${2:?usage: $0 <local data_gz dir> <bucket>}"

for f in "$src"/*.csv.gz; do
  table="$(basename "$f" .csv.gz)"
  aws s3 cp "$f" "s3://$bucket/$table/$table.csv.gz" --only-show-errors
  echo "uploaded $table"
done

for dir in "$src"/*/; do
  table="$(basename "$dir")"
  aws s3 sync "$dir" "s3://$bucket/$table/" --exclude ".DS_Store" --only-show-errors
  echo "synced $table"
done
