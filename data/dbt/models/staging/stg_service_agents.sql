with deduped as (
    -- No process_date in dimension files; duplicates are exact copies.
    {{ dedupe(source('latam_raw', 'service_agents'), 'agent_id', 'agent_id') }}
)

-- Agent names, email and phone are excluded: benchmarking uses agent_id only.
select
    {{ clean_str('agent_id') }}                   as agent_id,
    {{ clean_str('native_accent') }}              as native_accent,
    {{ clean_str('country_of_origin') }}          as country_of_origin,
    {{ clean_str('assigned_branch_id') }}         as assigned_branch_id,
    {{ clean_str('agent_type') }}                 as agent_type,
    {{ clean_str('experience_level') }}           as experience_level,
    {{ clean_str('languages') }}                  as languages,
    {{ clean_str('specialty') }}                  as specialty,
    {{ to_date('hire_date') }}                    as hire_date,
    {{ to_double('avg_csat') }}                   as reported_avg_csat,
    {{ to_int('total_monthly_interactions') }}    as reported_monthly_interactions,
    {{ clean_str('agent_status') }}               as agent_status,
    {{ clean_str('work_shift') }}                 as work_shift
from deduped
