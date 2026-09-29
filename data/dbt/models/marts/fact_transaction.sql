{#
  Grain: one row per financial transaction, with the product it was made with.
  Feeds the customer's movements in the demo (dashboard and the agent's tools)
  and transaction analytics (declines, fraud, disputes).
#}

with transactions as (
    select * from {{ ref('stg_transactions') }}
),

products as (
    select product_id, product_type, product_number_last4
    from {{ ref('dim_product') }}
)

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
    t.fraud_score

from transactions as t
left join products as p on p.product_id = t.product_id
