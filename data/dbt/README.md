# dbt: the data model

Turns the raw tables (`latam_raw`) into clean tables in `latam_curated`:

| Table | One row per | Notes |
|---|---|---|
| `dim_date` | day | |
| `dim_agent` | service agent | No personal contact data |
| `dim_customer` | customer | No direct identifiers (name, document, contact, exact birth date) |
| `dim_product` | customer product (accounts, cards, loans) | Latest snapshot; only the last 4 digits of the account/card number |
| `fact_interaction` | call center interaction | First contact resolution in `is_fcr` |
| `fact_transaction` | financial transaction | Product used, status (declines), fraud flags; no coordinates |

## Dev and prod
| Target | Where | Who builds it |
|---|---|---|
| `dev` (default) | `latam_curated_dev_<DBT_DEV_NAME>`, your own copy | You, as often as you like |
| `prod` | `latam_curated`, what notebooks, ML and the app read | Only the data pipeline ([.github/workflows/data.yml](../../.github/workflows/data.yml)), when a change to `data/dbt` reaches `main` |

`stg_*` and `dim_*`/`fact_*` are **layers**, not environments: staging cleans each raw table, marts are what people query. Both exist in dev and in prod.

## Rebuild after changing SQL
After the setup in [docs/setup.md](../../docs/setup.md), set your name once (lowercase, no spaces), then build into your own schema:

```bash
export DBT_DEV_NAME=yourname          # Windows PowerShell: $env:DBT_DEV_NAME="yourname"
cd data/dbt
uv run dbt build                      # -> latam_curated_dev_yourname
uv run dbt build --select +fact_transaction   # one model and what it depends on
```
`dbt build` creates the tables and runs the tests (a few cents: `fact_transaction` reads the 4.4 million transactions; the whole model takes about a minute). Warnings about relationships are expected: the dataset has broken links on purpose. Query your tables in Athena as `latam_curated_dev_yourname.<table>`.

To publish: open a PR (CI runs `dbt parse`), then the release to `main` rebuilds `latam_curated` with all tests. `uv run dbt build --target prod` by hand is only for emergencies.

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
