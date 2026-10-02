# data

Data pipeline code for the LATAM Bank dataset. Owner: Paul. The dataset itself is never committed (public repo).

- `scripts/upload_raw_data.sh`: uploads the gzipped original data to the `data-root` bucket.
- `scripts/convert_transcripts.py`: makes a Parquet copy of `call_transcripts` (its text has line breaks that Athena can't read from CSV). Upload it to `s3://fh26-hackaton-data/converted/call_transcripts/`.
- `dbt/`: the data model (`dim_*`, `fact_interaction`, `fact_transaction`). See `dbt/README.md`.

Curated tables are built in the `latam_curated` Glue database. Nulls are kept; the original data is never modified.
