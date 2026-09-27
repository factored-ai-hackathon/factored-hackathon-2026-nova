with deduped as (
    {{ dedupe(source('latam_raw', 'complaints'), 'complaint_id') }}
)

select
    {{ clean_str('complaint_id') }}          as complaint_id,
    {{ to_ts('creation_date') }}             as created_at,
    {{ clean_str('customer_id') }}           as customer_id,
    {{ clean_str('origin_interaction_id') }} as origin_interaction_id,
    {{ clean_str('assigned_agent_id') }}     as assigned_agent_id,
    {{ clean_str('case_type') }}             as case_type,
    {{ clean_str('category') }}              as category,
    {{ clean_str('priority') }}              as priority,
    {{ clean_str('status') }}                as status,
    {{ to_bool('sla_breached') }}            as sla_breached,
    {{ to_int('resolution_days') }}          as resolution_days
from deduped
