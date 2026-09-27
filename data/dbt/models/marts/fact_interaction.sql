{#
  Grain: one row per call center interaction.

  FCR (first contact resolution): the interaction was resolved AND the same
  customer did not contact us again about the same reason_category within
  var('fcr_window_days') days. NULL when it can't be judged: missing
  customer/reason/resolution, or the interaction is too close to the end of
  the dataset to see a repeat contact.

  Complaints are not linked: the dataset leaves origin_interaction_id empty on
  every complaint, so complaints are analysed on their own (stg_complaints).
#}

with interactions as (
    select * from {{ ref('stg_call_center_interactions') }}
),

with_next as (
    select
        *,
        case
            when customer_id is not null and reason_category is not null
            then lead(interaction_at) over (
                partition by customer_id, reason_category
                order by interaction_at, interaction_id
            )
        end as next_same_reason_at
    from interactions
),

-- One survey per interaction (latest), one transcript per interaction.
surveys as (
    select * from (
        select *, row_number() over (partition by interaction_id order by survey_at desc) as rn
        from {{ ref('stg_satisfaction_surveys') }}
        where interaction_id is not null
    ) where rn = 1
),

transcripts as (
    select * from (
        select *, row_number() over (partition by interaction_id order by transcript_id) as rn
        from {{ ref('stg_call_transcripts') }}
        where interaction_id is not null
    ) where rn = 1
),

scored as (
    select
        *,
        interaction_at <= date '{{ var("as_of_date") }}' - interval '{{ var("fcr_window_days") }}' day
            as fcr_observable,
        next_same_reason_at is not null
            and next_same_reason_at <= interaction_at + interval '{{ var("fcr_window_days") }}' day
            as repeat_contact_in_window
    from with_next
)

select
    -- keys
    i.interaction_id,
    i.customer_id,
    i.agent_id,
    cast(i.interaction_at as date)                  as date_day,
    i.interaction_at,
    i.process_date,

    -- descriptive attributes (degenerate dimensions)
    i.interaction_type,
    i.channel,
    i.contact_reason,
    i.reason_category,
    i.detected_sentiment,
    i.customer_detected_accent,
    i.agent_used_accent,
    case
        when i.customer_detected_accent is null or i.agent_used_accent is null then null
        else i.customer_detected_accent = i.agent_used_accent
    end                                             as accent_match,

    -- measures
    i.duration_seconds,
    i.wait_time_seconds,
    i.sentiment_score,
    i.was_resolved,
    i.requires_followup,
    i.was_escalated,
    i.has_transcript,
    i.has_recording,

    -- first contact resolution
    i.next_same_reason_at,
    case
        when i.customer_id is null or i.reason_category is null then null
        else i.repeat_contact_in_window
    end                                             as repeat_contact_in_window,
    case
        when not i.fcr_observable
          or i.customer_id is null
          or i.reason_category is null
          or i.was_resolved is null then null
        else i.was_resolved and not i.repeat_contact_in_window
    end                                             as is_fcr,

    -- survey outcome
    s.survey_id,
    s.survey_type,
    s.main_score                                    as survey_score,
    case when s.survey_type = 'CSAT' then s.main_score end as csat_score,
    case when s.survey_type = 'NPS'  then s.main_score end as nps_score,
    case when s.survey_type = 'CES'  then s.main_score end as ces_score,
    s.nps_category,
    s.comment_sentiment                             as survey_comment_sentiment,

    -- transcript metadata
    t.transcript_id,
    t.detected_intents                              as transcript_intents,
    t.main_topics                                   as transcript_topics

from scored as i
left join surveys     as s on s.interaction_id = i.interaction_id
left join transcripts as t on t.interaction_id = i.interaction_id
