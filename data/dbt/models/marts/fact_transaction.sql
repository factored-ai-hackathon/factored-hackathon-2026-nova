{#
  What readers query: the incremental table without its partition column. A view, so the stored
  table (fact_transaction_incr) can be rebuilt month by month without anyone reading a half-written
  one, and so the notebooks and data/scripts/load_demo_data.py keep working unchanged.
#}

{{ config(materialized='view') }}

select
    transaction_id, customer_id, product_id, date_day, transaction_at, process_date,
    product_type, product_number_last4,
    transaction_type, transaction_category, channel, branch_id, merchant_name, merchant_category,
    transaction_country, transaction_city, transaction_status, response_code,
    amount, currency, amount_usd, is_declined, is_fraud, fraud_score
from {{ ref('fact_transaction_incr') }}
