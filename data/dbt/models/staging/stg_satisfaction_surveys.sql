with deduped as (
    {{ dedupe(source('latam_raw', 'satisfaction_surveys'), 'survey_id') }}
)

-- Question texts and open comments are left out: free text belongs to the ML
-- work in ml/, not to the analytics model.
select
    {{ clean_str('survey_id') }}          as survey_id,
    {{ to_ts('survey_date') }}            as survey_at,
    {{ clean_str('interaction_id') }}     as interaction_id,
    {{ clean_str('customer_id') }}        as customer_id,
    {{ clean_str('agent_id') }}           as agent_id,
    {{ clean_str('survey_type') }}        as survey_type,
    {{ clean_str('send_channel') }}       as send_channel,
    {{ to_int('main_score') }}            as main_score,
    {{ clean_str('nps_category') }}       as nps_category,
    {{ clean_str('comment_sentiment') }}  as comment_sentiment,
    {{ to_double('response_time_hours') }} as response_time_hours
from deduped
