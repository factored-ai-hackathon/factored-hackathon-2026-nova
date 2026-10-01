{#
  TEST FIXTURE (only with --vars '{include_fixture_batch: 2}'). The re-delivery corrects
  FIXTURE-0003 in place: still one row, now Approved, with the newer process_date; and the new
  FIXTURE-0006 is there. Returns the expectations that are not met.
#}
{% if var('include_fixture_batch', 0) | int < 2 %}
select 1 as skipped where 1 = 0
{% else %}
select 'FIXTURE-0003 must exist once, Approved, delivered 2026-06-19' as expectation,
       count(*) as copies, max(transaction_status) as status, max(process_date) as delivered
from {{ ref('fact_transaction_incr') }}
where transaction_id = 'FIXTURE-0003'
having count(*) <> 1 or max(transaction_status) <> 'Approved' or max(process_date) <> date '2026-06-19'

union all

select 'FIXTURE-0006 must exist once', count(*), max(transaction_status), max(process_date)
from {{ ref('fact_transaction_incr') }}
where transaction_id = 'FIXTURE-0006'
having count(*) <> 1
{% endif %}
