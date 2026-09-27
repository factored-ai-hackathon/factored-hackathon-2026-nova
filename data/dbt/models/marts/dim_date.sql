-- Athena's sequence() needs timestamps; everything is cast back to date
-- (Athena can't write timestamp(0) to Parquet).
with days as (
    select cast(ts as date) as d
    from unnest(
        sequence(
            timestamp '{{ var("date_spine_start") }} 00:00:00',
            timestamp '{{ var("date_spine_end") }} 00:00:00',
            interval '1' day
        )
    ) as t(ts)
)

select
    d                                       as date_day,
    year(d)                                 as year,
    month(d)                                as month,
    day(d)                                  as day_of_month,
    day_of_week(d)                          as day_of_week,   -- 1 = Monday
    week_of_year(d)                         as week_of_year,
    cast(date_trunc('month', d) as date)    as month_start,
    cast(date_trunc('week', d) as date)     as week_start,
    day_of_week(d) in (6, 7)                as is_weekend
from days
