{#
  Freshness, warning level: the same check with the tighter freshness_warn_days. A warning means
  "look at it"; the error level stops the pipeline.
#}
{{ config(severity='warn') }}

select
    max(process_date) as newest_delivery,
    date '{{ var("as_of_date") }}' as as_of_date,
    {{ var('freshness_warn_days') }} as allowed_days_behind
from {{ ref('fact_transaction') }}
having max(process_date) is null
    or max(process_date) < date_add('day', -{{ var('freshness_warn_days') }}, date '{{ var("as_of_date") }}')
