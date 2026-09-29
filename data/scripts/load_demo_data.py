"""Load the whole dataset's customers into the DynamoDB demo-customers table.

The chat agent can't query Athena per message (seconds per query, cost per scan), so every
customer is copied into DynamoDB, one partition per customer:

    PROFILE        identity for the login and verification (latam_raw: the curated schema drops
                   identifiers on purpose; the dataset is fully synthetic)
    PRODUCT#<id>   latam_curated.dim_product (last 4 digits of the number only)
    TXN#<ts>#<id>  latam_curated.fact_transaction
    COMPLAINT#<id> latam_curated.stg_complaints

plus one index item (customer_id "#index") with the demo scenarios and a pool of random customers,
written last, so the demo login never offers a customer whose items aren't loaded yet.

Athena exports each table to S3 as Parquet (UNLOAD, through awswrangler) and the rows are written
in parallel batches. Items are keyed by their ids, so a rerun overwrites them: to resume after an
interruption, run again (optionally --only the kinds that didn't finish).

Usage (from the repo root, Paul runs it):
    AWS_PROFILE=hackathon uv run python data/scripts/load_demo_data.py --dry-run
    AWS_PROFILE=hackathon uv run python data/scripts/load_demo_data.py
    AWS_PROFILE=hackathon uv run python data/scripts/load_demo_data.py --only TXN,INDEX

Only the last 4 digits of the phone are stored. Nothing is printed except counts.
"""

import argparse
import math
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import awswrangler as wr
import boto3
import pandas as pd
from botocore.config import Config

REGION = "us-east-2"
WORKGROUP = "hackathon"
RAW_DB = "latam_raw"
CURATED_DB = "latam_curated"
TABLE = "fh26-demo-customers"
EXPORT_PREFIX = "s3://fh26-hackaton-data/athena-results/demo-loader/"
AS_OF = "2026-06-17"  # dataset end (dbt var as_of_date)
POOL_SIZE = 1000  # random customers the demo login picks from (the index item must stay < 400 KB)
SCENARIO_SIZE = 20  # candidate customers per scenario
WRITERS = 8  # parallel batch writers (--writers)

# Uppercase letters and digits: passports have letters (backend: identity.normalize_document).
DOCUMENT = "upper(regexp_replace(coalesce(c.document_number, ''), '[^0-9A-Za-z]', ''))"
PHONE_DIGITS = "regexp_replace(coalesce(c.mobile_phone, ''), '[^0-9]', '')"

PROFILE_SQL = f"""
select c.customer_id, trim(c.first_name) as first_name, trim(c.country) as country,
       trim(c.document_type) as document_type, {DOCUMENT} as document_number,
       cast(try_cast(trim(c.date_of_birth) as date) as varchar) as birth_date,
       nullif(substr({PHONE_DIGITS}, -4), '') as phone_last4
from (select *, row_number() over (partition by customer_id order by last_updated desc) rn
      from {RAW_DB}.customers) c
where c.rn = 1 and nullif(trim(c.customer_id), '') is not null
"""

# kind -> (query, sort key built from a row)
KINDS: dict[str, tuple[str, Any]] = {
    "PROFILE": (PROFILE_SQL, lambda r: "PROFILE"),
    "PRODUCT": (
        f"select * from {CURATED_DB}.dim_product",
        lambda r: f"PRODUCT#{r['product_id']}",
    ),
    "TXN": (
        f"select * from {CURATED_DB}.fact_transaction",
        lambda r: f"TXN#{r.get('transaction_at') or '0000'}#{r['transaction_id']}",
    ),
    "COMPLAINT": (
        f"select * from {CURATED_DB}.stg_complaints",
        lambda r: f"COMPLAINT#{r['complaint_id']}",
    ),
}
ID_COLUMN = {
    "PROFILE": "customer_id",
    "PRODUCT": "product_id",
    "TXN": "transaction_id",
    "COMPLAINT": "complaint_id",
}

# Customers who can log in (a mobile phone for the code) and show each demo path. Picked by a hash
# of customer_id, so reruns offer the same people (docs/demo.md stays valid).
LOGIN_READY = f"""
select c.customer_id from (select *, row_number() over (partition by customer_id
                                                        order by last_updated desc) rn
                           from {RAW_DB}.customers) c
where c.rn = 1 and length({PHONE_DIGITS}) >= 4
"""
SCENARIOS = {
    # A card payment declined for insufficient funds in the last 30 days.
    "declined_transaction": f"""
        select distinct customer_id from {CURATED_DB}.fact_transaction
        where transaction_status = 'Declined' and response_code = '51'
          and transaction_at >= date '{AS_OF}' - interval '30' day""",
    # A complaint still being handled: the path that ends with a human.
    "open_complaint": f"""
        select distinct customer_id from {CURATED_DB}.stg_complaints
        where status in ('Open', 'In Process', 'Escalated')""",
    # A product more than 30 days past due.
    "past_due": f"""
        select distinct customer_id from {CURATED_DB}.dim_product where days_past_due > 30""",
}


def athena(sql: str, database: str, export: bool = False):
    """Run a query. export=True: large results, UNLOADed to Parquet and read in chunks. UNLOAD needs
    an empty destination, so each export gets its own prefix. Otherwise a normal query (small
    results, read from the workgroup's result file)."""
    session = boto3.Session(region_name=REGION)
    if export:
        return wr.athena.read_sql_query(
            sql,
            database=database,
            workgroup=WORKGROUP,
            ctas_approach=False,
            unload_approach=True,
            s3_output=f"{EXPORT_PREFIX}{uuid.uuid4().hex}/",
            chunksize=True,
            boto3_session=session,
        )
    return wr.athena.read_sql_query(
        sql, database=database, workgroup=WORKGROUP, ctas_approach=False, boto3_session=session
    )


def count(sql: str, database: str) -> int:
    df = athena(f"select count(*) as n from ({sql})", database)
    return int(df["n"].iloc[0])


def to_attribute(value: Any) -> Any:
    """DynamoDB types: numbers as Decimal, dates/timestamps as ISO text, missing values dropped."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float):
        return None if math.isnan(value) else Decimal(str(value))
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, pd.Timestamp | datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalars
        return to_attribute(value.item())
    return value


def items_from(kind: str, df: pd.DataFrame) -> list[dict]:
    sort_key = KINDS[kind][1]
    id_column = ID_COLUMN[kind]
    items = []
    for row in df.to_dict("records"):
        values = {k: to_attribute(v) for k, v in row.items()}
        values = {k: v for k, v in values.items() if v is not None and v != ""}
        # dbt keeps rows with an empty key (reported by its tests); they can't be addressed here.
        if not values.get("customer_id") or not values.get(id_column):
            continue
        items.append({**values, "sk": sort_key(values)})
    return items


def write(items: list[dict]) -> None:
    """Write in parallel batches; the batch writer retries unprocessed items."""
    if not items:
        return
    config = Config(retries={"mode": "adaptive", "max_attempts": 10})

    def worker(part: list[dict]) -> None:
        table = boto3.resource("dynamodb", region_name=REGION, config=config).Table(TABLE)
        with table.batch_writer(overwrite_by_pkeys=["customer_id", "sk"]) as batch:
            for item in part:
                batch.put_item(Item=item)

    size = math.ceil(len(items) / WRITERS)
    with ThreadPoolExecutor(max(WRITERS, 1)) as pool:
        list(pool.map(worker, [items[i : i + size] for i in range(0, len(items), size)]))


def set_writers(n: int) -> None:
    global WRITERS
    WRITERS = max(1, n)


def load(kind: str) -> int:
    sql, _ = KINDS[kind]
    database = RAW_DB if kind == "PROFILE" else CURATED_DB
    written, started = 0, time.monotonic()
    for chunk in athena(sql, database, export=True):
        items = items_from(kind, chunk)
        write(items)
        written += len(items)
        rate = written / max(time.monotonic() - started, 1e-6)
        print(f"  {kind}: {written:,} items ({rate:,.0f}/s)", flush=True)
    return written


def pick(sql: str, n: int) -> list[str]:
    """n customers from `sql` who can log in, in a stable order (hash of customer_id)."""
    query = f"""
        select s.customer_id from ({sql}) s join ({LOGIN_READY}) r on r.customer_id = s.customer_id
        order by to_hex(md5(to_utf8(s.customer_id))) limit {int(n)}"""
    return athena(query, RAW_DB)["customer_id"].tolist()


def build_index() -> dict:
    return {
        "customer_id": "#index",
        "sk": "DEMO_CUSTOMERS",
        "customer_ids": pick(LOGIN_READY, POOL_SIZE),
        "scenarios": {key: pick(sql, SCENARIO_SIZE) for key, sql in SCENARIOS.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="count rows only, write nothing")
    parser.add_argument(
        "--only", default="PROFILE,PRODUCT,TXN,COMPLAINT,INDEX", help="comma-separated kinds"
    )
    parser.add_argument("--writers", type=int, default=WRITERS, help="parallel batch writers")
    args = parser.parse_args()
    set_writers(args.writers)
    kinds = [k.strip().upper() for k in args.only.split(",") if k.strip()]
    unknown = set(kinds) - {*KINDS, "INDEX"}
    if unknown:
        parser.error(f"unknown kinds: {sorted(unknown)}")

    if args.dry_run:
        total = 0
        for kind in (k for k in kinds if k in KINDS):
            sql, _ = KINDS[kind]
            n = count(sql, RAW_DB if kind == "PROFILE" else CURATED_DB)
            total += n
            print(f"{kind}: {n:,} rows")
        if "INDEX" in kinds:
            index = build_index()
            sizes = {k: len(v) for k, v in index["scenarios"].items()}
            print(f"INDEX: pool {len(index['customer_ids'])}, scenarios {sizes}")
        # On-demand: 1 write request unit per item under 1 KB (most are).
        print(f"~{total:,} items to write, roughly {total / 1e6:.1f}M write request units")
        return

    for kind in (k for k in kinds if k in KINDS):
        print(f"{kind}: exporting from Athena and writing to {TABLE}", flush=True)
        print(f"{kind}: done, {load(kind):,} items")
    if "INDEX" in kinds:
        index = build_index()
        boto3.resource("dynamodb", region_name=REGION).Table(TABLE).put_item(Item=index)
        sizes = {k: len(v) for k, v in index["scenarios"].items()}
        print(f"INDEX: pool {len(index['customer_ids'])}, scenarios {sizes}")


if __name__ == "__main__":
    main()
