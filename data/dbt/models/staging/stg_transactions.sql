{#
  Financial transactions, deduplicated (latest process_date wins, so late
  re-deliveries replace earlier ones). Latitude/longitude are dropped: precise
  location isn't needed and is personal data; country and city are kept.
#}

with deduped as (
    {{ dedupe(source('latam_raw', 'transactions'), 'transaction_id') }}
)

select
    {{ clean_str('transaction_id') }}               as transaction_id,
    {{ to_ts('transaction_date') }}                 as transaction_at,
    {{ to_date('process_date') }}                   as process_date,
    {{ clean_str('product_id') }}                   as product_id,
    {{ clean_str('customer_id') }}                  as customer_id,
    {{ clean_str('transaction_type') }}             as transaction_type,
    {{ clean_str('transaction_category') }}         as transaction_category,
    {{ to_double('amount') }}                       as amount,
    {{ clean_str('currency') }}                     as currency,
    {{ to_double('amount_usd') }}                   as amount_usd,
    {{ clean_str('channel') }}                      as channel,
    {{ clean_str('branch_id') }}                    as branch_id,
    {{ clean_str('merchant_name') }}                as merchant_name,
    {{ clean_str('merchant_category') }}            as merchant_category,
    {{ clean_str('transaction_country') }}          as transaction_country,
    {{ clean_str('transaction_city') }}             as transaction_city,
    {{ clean_str('transaction_status') }}           as transaction_status,
    {{ clean_str('response_code') }}                as response_code,
    {{ to_bool('is_fraud') }}                       as is_fraud,
    {{ to_double('fraud_score') }}                  as fraud_score
from deduped
