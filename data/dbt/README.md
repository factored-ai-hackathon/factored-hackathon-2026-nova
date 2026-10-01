# dbt: the data model

Turns the raw tables (`latam_raw`) into clean tables in `latam_curated`:

| Table | One row per | Notes |
|---|---|---|
| `dim_date` | day | |
| `dim_agent` | service agent | No personal contact data |
| `dim_customer` | customer | No direct identifiers (name, document, contact, exact birth date) |
| `dim_product` | customer product (accounts, cards, loans) | Latest snapshot; only the last 4 digits of the account/card number |
| `fact_interaction` | call center interaction | First contact resolution in `is_fcr` |
| `fact_transaction` | financial transaction | Product used, status (declines), fraud flags; no coordinates. A view over `fact_transaction_incr`, the incremental table partitioned by month (see "Updates and freshness") |

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

## Updates and freshness
The challenge asks for an update and freshness policy, shown with a labeled test fixture because the dataset is a static snapshot (it ends 2026-06-17; no real delivery will ever arrive).

| Topic | Policy |
|---|---|
| Deliveries | Raw `transactions` arrive as daily files (`year/month/day`); `process_date` is the delivery date. A transaction can be delivered again later (a correction or a late arrival) with a newer `process_date` |
| Which delivery wins | The latest `process_date` of each `transaction_id` (`dedupe` in `stg_transactions`). A re-delivery replaces the earlier row: it never adds a second one |
| Incremental update | `fact_transaction_incr` is partitioned by the month of the transaction. The first run builds everything. Each later run finds the months that received a delivery newer than the table's latest `process_date` minus `late_arrival_lookback_days` (3) and **rewrites those months completely** from the deduplicated staging table. A late arrival dated months back therefore lands in its own month, and running the same delivery twice gives the same table (idempotent) |
| Freshness | The newest `process_date` in `fact_transaction` must be within `freshness_warn_days` (1: warning) and `freshness_error_days` (3: the pipeline stops) of `as_of_date`. For a live feed `as_of_date` would be today; here it is the end of the data |
| Readers | They query `fact_transaction`, a view that hides the partition column, so the stored table can be rebuilt month by month and `data/scripts/load_demo_data.py`, notebooks and the app are unchanged |
| When it runs | In the **Data pipeline** job of the Deploy workflow, on every merge to `main`; skipped when the merge changed nothing in `data/dbt`, `uv.lock` or `pyproject.toml`. By hand: Actions → Data pipeline → Run workflow (`full_refresh` rebuilds the table from scratch) |
| Not handled | Deleted transactions (a delivery cannot remove a row), a delivery older than the lookback with a `process_date` older than the table's latest, and more than 100 months of history (Athena's partition limit per write) |

### The test fixture (synthetic, never in prod)
`seeds/fixture_transactions.csv` is a pretend delivery: every id starts with `FIXTURE-`, with no real customer, product or merchant. Batch 1 adds three new transactions after the end of the data and two **late arrivals dated 2025-11**; batch 2 re-delivers `FIXTURE-0003` corrected (Pending → Approved) and adds one more. It is only built outside prod (`seeds: +enabled`), only used with `--vars '{include_fixture_batch: 1}'` (or 2), and `stg_transactions` refuses it in prod.

```bash
cd data/dbt && AWS_PROFILE=hackathon DBT_DEV_NAME=yourname ./fixture_check.sh   # ~10 min, in your own dev schema
```
The script builds the baseline, applies the deliveries and runs the `fixture` tests, then cleans up. What it showed (Oct 2, dev schema, 4.4 million rows):

| Step | Rows | Newest delivery | Result |
|---|---|---|---|
| 0. baseline (full build) | 4,425,008 | 2026-06-17 | 26/26 models and tests pass; freshness passes |
| 1. batch 1 | 4,425,013 (+5) | 2026-06-18 | `FIXTURE-0004` and `-0005` sit in 2025-11, the others in 2026-06; fixture tests pass |
| 2. batch 1 again | 4,425,013 (+0) | 2026-06-18 | idempotent: nothing changes |
| 3. batch 2 | 4,425,014 (+1) | 2026-06-19 | `FIXTURE-0003` is one row, now Approved, with the newer delivery date; `FIXTURE-0006` added |
| 4. full refresh, no fixture | 4,425,008 | 2026-06-17 | the schema is clean again |

Warnings in steps 1 to 3 are the expected `relationships` ones (the fixture's customer and product are not in the dimensions, as the dataset's own broken links already are).

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
