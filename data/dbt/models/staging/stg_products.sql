{#
  Customer products (accounts, cards, loans...), latest snapshot per product.
  The full account/card number is dropped: only its last 4 digits are kept,
  the way banking apps show it.
#}

with deduped as (
    {{ dedupe(source('latam_raw', 'products'), 'product_id', 'last_updated desc') }}
)

select
    {{ clean_str('product_id') }}                   as product_id,
    {{ clean_str('customer_id') }}                  as customer_id,
    {{ clean_str('product_type') }}                 as product_type,
    nullif(substr(regexp_replace(coalesce(product_number, ''), '[^0-9]', ''), -4), '')
                                                    as product_number_last4,
    {{ clean_str('currency') }}                     as currency,
    {{ to_double('current_balance') }}              as current_balance,
    {{ to_double('credit_limit') }}                 as credit_limit,
    {{ to_double('interest_rate') }}                as interest_rate,
    {{ to_date('opening_date') }}                   as opening_date,
    {{ to_date('expiration_date') }}                as expiration_date,
    {{ clean_str('opening_branch_id') }}            as opening_branch_id,
    {{ clean_str('product_status') }}               as product_status,
    {{ clean_str('opening_channel') }}              as opening_channel,
    {{ to_bool('has_linked_app') }}                 as has_linked_app,
    {{ to_int('days_past_due') }}                   as days_past_due,
    {{ to_ts('last_transaction_date') }}            as last_transaction_at,
    {{ to_ts('last_updated') }}                     as last_updated_at
from deduped
