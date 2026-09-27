with deduped as (
    {{ dedupe(source('latam_raw', 'call_transcripts'), 'transcript_id') }}
)

-- Transcript text (full_text, customer_text, agent_text) is excluded here and
-- read directly by the NLP work in ml/. Only metadata goes to the model.
select
    {{ clean_str('transcript_id') }}       as transcript_id,
    {{ clean_str('interaction_id') }}      as interaction_id,
    {{ clean_str('detected_language') }}   as detected_language,
    {{ clean_str('detected_accent') }}     as detected_accent,
    {{ to_double('accent_confidence') }}   as accent_confidence,
    {{ clean_str('detected_intents') }}    as detected_intents,
    {{ clean_str('main_topics') }}         as main_topics,
    {{ clean_str('audio_quality') }}       as audio_quality,
    {{ to_int('duration_seconds') }}       as duration_seconds
from deduped
