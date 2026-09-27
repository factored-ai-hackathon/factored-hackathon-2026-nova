# dbt: the data model

Turns the raw tables (`latam_raw`) into clean tables in `latam_curated`: `dim_date`, `dim_agent`, `dim_customer` and `fact_interaction` (one row per call center interaction, with first contact resolution in `is_fcr`).

## Rebuild after changing SQL
After the setup in [docs/setup.md](../../docs/setup.md):

```bash
cd data/dbt
uv run dbt build
```
`dbt build` creates the tables and runs the tests (about $0.01). Warnings about relationships are expected: the dataset has broken links on purpose.

## Raw tables (first time, or after changing their columns)
The raw tables in `latam_raw` are defined in `models/staging/_sources.yml` (one list of columns per table). To create them, or recreate them after editing that file:

```bash
uv run dbt run-operation create_raw_tables --args '{replace: true}'
```
This only changes table definitions; the original files in S3 are never touched. No Terraform needed.

## Where things are
- `models/staging/`: one cleaned table per source table (typed, duplicates removed, personal data removed)
- `models/marts/`: the dimension and fact tables people query
- `models/staging/_sources.yml`: the raw tables and their columns
- `macros/create_raw_tables.sql`: creates the raw tables from that file
- `macros/casts.sql`: helpers for converting text to numbers, dates and booleans
