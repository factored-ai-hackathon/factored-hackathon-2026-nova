#!/usr/bin/env bash
# Shows that the incremental update of fact_transaction is correct, with the labeled test fixture
# (seeds/fixture_transactions.csv). Builds in YOUR dev schema (latam_curated_dev_$DBT_DEV_NAME),
# never in prod, and leaves the schema clean at the end.
#
#   cd data/dbt && AWS_PROFILE=hackathon DBT_DEV_NAME=yourname ./fixture_check.sh
#
# 0. full build, no fixture                      -> the baseline
# 1. first delivery (batch 1)                    -> +5 rows; two late arrivals land in their own month
# 2. the same delivery again                     -> nothing changes (idempotent)
# 3. re-delivery (batch 2)                       -> +1 new row; FIXTURE-0003 corrected in place
# 4. full refresh, no fixture                    -> back to the baseline (the schema is clean)
set -euo pipefail
cd "$(dirname "$0")"
: "${DBT_DEV_NAME:?set DBT_DEV_NAME (your name, lowercase)}"

count() {
  uv run dbt show --quiet --inline "select count(*) as rows_, count(distinct transaction_id) as ids, max(process_date) as newest_delivery from {{ ref('fact_transaction') }}" 2>/dev/null \
    | grep -E "^\|" | tail -1
}
build() {  # $1 = fixture batch
  uv run dbt build --select stg_transactions fact_transaction_incr fact_transaction --vars "{include_fixture_batch: $1}" > "target/fixture_build_$1.log" 2>&1
  grep -E "Done\.|ERROR" "target/fixture_build_$1.log" | tail -2
}

echo "== 0. baseline (full build, no fixture)"
uv run dbt seed --select fixture_transactions > /dev/null 2>&1
uv run dbt build --select +fact_transaction --full-refresh > target/fixture_build_base.log 2>&1
grep -E "Done\.|ERROR" target/fixture_build_base.log | tail -2
echo "rows | distinct ids | newest delivery"; count

echo "== 1. first delivery: 3 new transactions + 2 late arrivals dated 2025-11"
build 1
count
uv run dbt test --select tag:fixture --vars "{include_fixture_batch: 1}" 2>&1 | grep -E "PASS|FAIL|ERROR|Done" | tail -4

echo "== 2. the same delivery again (idempotent)"
build 1
count

echo "== 3. re-delivery: FIXTURE-0003 Pending -> Approved, plus one new transaction"
build 2
count
uv run dbt test --select tag:fixture --vars "{include_fixture_batch: 2}" 2>&1 | grep -E "PASS|FAIL|ERROR|Done" | tail -4
uv run dbt show --quiet --inline "select transaction_id, txn_month, transaction_status, process_date from {{ ref('fact_transaction_incr') }} where transaction_id like 'FIXTURE-%' order by 1" 2>/dev/null | grep -E "^\|"

echo "== 4. clean up (full refresh, no fixture)"
uv run dbt build --select +fact_transaction --full-refresh > target/fixture_build_clean.log 2>&1
grep -E "Done\.|ERROR" target/fixture_build_clean.log | tail -2
count
