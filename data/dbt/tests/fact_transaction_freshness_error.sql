{#
  Freshness, error level: the newest delivery (process_date) in fact_transaction must be within
  freshness_error_days of as_of_date, the end of the data. Returns a row (and fails) when it is not.
  In a live feed as_of_date would be today; the data here is a snapshot, so it is the dataset's end.
#}
{{ config(severity='error') }}

select
    max(process_date) as newest_delivery,
    date '{{ var("as_of_date") }}' as as_of_date,
    {{ var('freshness_error_days') }} as allowed_days_behind
from {{ ref('fact_transaction') }}
having max(process_date) is null
    or max(process_date) < date_add('day', -{{ var('freshness_error_days') }}, date '{{ var("as_of_date") }}')
