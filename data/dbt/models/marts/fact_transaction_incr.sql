{{
    config(
        materialized='incremental',
        incremental_strategy='insert_overwrite',
        partitioned_by=['txn_month'],
        on_schema_change='append_new_columns'
    )
}}

{#
  The stored, incremental table behind fact_transaction (readers use the view of that name).

  Grain: one row per financial transaction, with the product it was made with.
  Feeds the customer's movements in the demo (dashboard and the agent's tools)
  and transaction analytics (declines, fraud, disputes).

  Update policy (README, "Updates and freshness"):
  - Partitioned by month of the transaction (txn_month, 'YYYY-MM').
  - The first run builds everything. Every later run finds the months that received a delivery
    (process_date newer than the table's latest minus late_arrival_lookback_days: new days, late
    arrivals dated months back, corrections of earlier rows) and rewrites those months completely
    from the deduplicated staging table, where the latest process_date of each transaction wins.
    Rewriting a whole month cannot duplicate a row or lose one, and running it twice gives the same
    table (idempotent).
#}

{% set month = "coalesce(date_format(transaction_at, '%Y-%m'), 'unknown')" %}


with transactions as (
    select * from {{ ref('stg_transactions') }}
),

products as (
    select product_id, product_type, product_number_last4
    from {{ ref('dim_product') }}
)

{% if is_incremental() %}
,

touched_months as (
    select distinct {{ month }} as txn_month
    from transactions
    where process_date >= date_add(
        'day', -{{ var('late_arrival_lookback_days') }}, (select max(process_date) from {{ this }})
    )
)
{% endif %}

select
    -- keys
    t.transaction_id,
    t.customer_id,
    t.product_id,
    cast(t.transaction_at as date)                  as date_day,
    t.transaction_at,
    t.process_date,

    -- product (degenerate: type and masked number)
    p.product_type,
    p.product_number_last4,

    -- descriptive attributes
    t.transaction_type,
    t.transaction_category,
    t.channel,
    t.branch_id,
    t.merchant_name,
    t.merchant_category,
    t.transaction_country,
    t.transaction_city,
    t.transaction_status,
    t.response_code,

    -- measures
    t.amount,
    t.currency,
    t.amount_usd,
    t.transaction_status = 'Declined'               as is_declined,
    t.is_fraud,
    t.fraud_score,

    -- partition (last column)
    {{ month.replace('transaction_at', 't.transaction_at') }} as txn_month

from transactions as t
left join products as p on p.product_id = t.product_id
{% if is_incremental() %}
where {{ month.replace('transaction_at', 't.transaction_at') }} in (select txn_month from touched_months)
{% endif %}
