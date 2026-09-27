with deduped as (
    {{ dedupe(source('latam_raw', 'customers'), 'customer_id', 'last_updated desc') }}
)

-- Direct identifiers are excluded (document number, names, email, phones,
-- address, postal code, exact birth date). Analytics and ML use customer_id
-- plus these non-identifying attributes; age is computed at the dataset end date (var as_of_date).
select
    {{ clean_str('customer_id') }}                        as customer_id,
    {{ clean_str('gender') }}                             as gender,
    date_diff('year', {{ to_date('date_of_birth') }}, date '{{ var("as_of_date") }}') as age_years,
    {{ clean_str('city') }}                               as city,
    {{ clean_str('state') }}                              as state,
    {{ clean_str('country') }}                            as country,
    {{ clean_str('detected_accent') }}                    as detected_accent,
    {{ clean_str('segment') }}                            as segment,
    {{ to_int('credit_score') }}                          as credit_score,
    {{ to_double('estimated_monthly_income') }}           as estimated_monthly_income,
    {{ clean_str('occupation') }}                         as occupation,
    {{ clean_str('marital_status') }}                     as marital_status,
    {{ clean_str('education_level') }}                    as education_level,
    {{ to_ts('registration_date') }}                      as registered_at,
    {{ clean_str('registration_branch_id') }}             as registration_branch_id,
    {{ clean_str('customer_status') }}                    as customer_status,
    {{ to_bool('accepts_marketing') }}                    as accepts_marketing,
    {{ to_ts('last_updated') }}                           as last_updated_at
from deduped
