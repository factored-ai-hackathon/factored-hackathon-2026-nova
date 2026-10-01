{#
  Financial transactions, deduplicated (latest process_date wins, so late
  re-deliveries replace earlier ones). Latitude/longitude are dropped: precise
  location isn't needed and is personal data; country and city are kept.
#}

{% set columns = [
    'transaction_id', 'transaction_date', 'process_date', 'product_id', 'customer_id',
    'transaction_type', 'transaction_category', 'amount', 'currency', 'amount_usd', 'channel',
    'branch_id', 'merchant_name', 'merchant_category', 'transaction_country', 'transaction_city',
    'transaction_status', 'response_code', 'is_fraud', 'fraud_score'
] %}

{#
  TEST FIXTURE: with --vars '{include_fixture_batch: 1}' (or 2) the rows of the synthetic,
  clearly labeled seeds/fixture_transactions.csv are added to the raw rows, as if a new delivery
  had arrived. Used to show the incremental update is correct (README, "Updates and freshness").
  Refused in prod: the fixture must never reach the published tables.
#}
{% set fixture_batch = var('include_fixture_batch', 0) | int %}
{% if fixture_batch > 0 and target.name == 'prod' %}
  {{ exceptions.raise_compiler_error('include_fixture_batch is a test fixture: it never runs in prod') }}
{% endif %}

with raw as (
    select {{ columns | join(', ') }}
    from {{ source('latam_raw', 'transactions') }}
    {% if fixture_batch > 0 %}
    union all
    select {{ columns | join(', ') }}
    from {{ ref('fixture_transactions') }}
    where cast(batch as integer) <= {{ fixture_batch }}
    {% endif %}
),

deduped as (
    {{ dedupe('raw', 'transaction_id') }}
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
