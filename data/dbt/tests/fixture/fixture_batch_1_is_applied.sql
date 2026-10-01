{#
  TEST FIXTURE (only with --vars '{include_fixture_batch: 1}' or 2). After the first delivery:
  FIXTURE-0001..0005 each exist exactly once, the two late arrivals (0004, 0005) sit in their own
  month (2025-11), not in the month of the delivery, and the rest in 2026-06.
  Returns the expectations that are not met.
#}
{% if var('include_fixture_batch', 0) | int < 1 %}
select 1 as skipped where 1 = 0
{% else %}
with expected as (
    select * from (values
        ('FIXTURE-0001', '2026-06'), ('FIXTURE-0002', '2026-06'), ('FIXTURE-0003', '2026-06'),
        ('FIXTURE-0004', '2025-11'), ('FIXTURE-0005', '2025-11')
    ) as t (transaction_id, txn_month)
),

found as (
    select transaction_id, txn_month, count(*) as copies
    from {{ ref('fact_transaction_incr') }}
    where transaction_id like 'FIXTURE-%'
    group by 1, 2
)

select e.transaction_id, e.txn_month as expected_month, f.txn_month as found_month, f.copies
from expected as e
left join found as f on f.transaction_id = e.transaction_id
where f.transaction_id is null or f.txn_month <> e.txn_month or f.copies <> 1
{% endif %}
