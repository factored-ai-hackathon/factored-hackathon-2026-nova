with deduped as (
    {{ dedupe(source('latam_raw', 'call_center_interactions'), 'interaction_id') }}
)

select
    {{ clean_str('interaction_id') }}           as interaction_id,
    {{ to_ts('interaction_date') }}             as interaction_at,
    {{ to_date('process_date') }}               as process_date,
    {{ clean_str('customer_id') }}              as customer_id,
    {{ clean_str('agent_id') }}                 as agent_id,
    {{ clean_str('interaction_type') }}         as interaction_type,
    {{ clean_str('channel') }}                  as channel,
    {{ clean_str('contact_reason') }}           as contact_reason,
    {{ clean_str('reason_category') }}          as reason_category,
    {{ to_int('duration_seconds') }}            as duration_seconds,
    {{ to_int('wait_time_seconds') }}           as wait_time_seconds,
    {{ to_bool('was_resolved') }}               as was_resolved,
    {{ to_bool('requires_followup') }}          as requires_followup,
    {{ clean_str('detected_sentiment') }}       as detected_sentiment,
    {{ to_double('sentiment_score') }}          as sentiment_score,
    {{ clean_str('customer_detected_accent') }} as customer_detected_accent,
    {{ clean_str('agent_used_accent') }}        as agent_used_accent,
    {{ to_bool('was_escalated') }}              as was_escalated,
    {{ clean_str('mentioned_products') }}       as mentioned_products,
    {{ to_bool('has_transcript') }}             as has_transcript,
    {{ to_bool('has_recording') }}              as has_recording
from deduped
