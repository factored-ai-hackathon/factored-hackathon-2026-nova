{# Grain: one row per customer product (latest snapshot). #}

select
    *,
    product_type in ('Credit Card', 'Personal Loan', 'Mortgage') as is_credit_product
from {{ ref('stg_products') }}
