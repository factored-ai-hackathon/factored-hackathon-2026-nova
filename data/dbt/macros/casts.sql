{# Raw tables are all STRING (OpenCSVSerde). These helpers type them without
   dropping rows: values that can't be parsed become NULL, and empty strings
   become NULL so missing data is explicit. #}

{% macro clean_str(col) -%}
  nullif(trim({{ col }}), '')
{%- endmacro %}

{% macro to_bool(col) -%}
  try_cast(lower(nullif(trim({{ col }}), '')) as boolean)
{%- endmacro %}

{# Numbers like '253.0' need to go through double before integer. #}
{% macro to_int(col) -%}
  cast(try_cast(nullif(trim({{ col }}), '') as double) as integer)
{%- endmacro %}

{% macro to_double(col) -%}
  try_cast(nullif(trim({{ col }}), '') as double)
{%- endmacro %}

{% macro to_ts(col) -%}
  try_cast(nullif(trim({{ col }}), '') as timestamp)
{%- endmacro %}

{% macro to_date(col) -%}
  try_cast(nullif(trim({{ col }}), '') as date)
{%- endmacro %}

{# Keep one row per business key: exact duplicates and late re-deliveries
   collapse to the most recent process_date. Rows with an empty key can't be
   matched to each other, so they are all kept (and reported by the not_null
   tests) instead of being collapsed into one. #}
{% macro dedupe(relation, key, order_by="process_date desc") -%}
  select * from (
    select *, row_number() over (partition by {{ key }} order by {{ order_by }}) as _rn
    from {{ relation }}
  ) where _rn = 1 or nullif(trim({{ key }}), '') is null
{%- endmacro %}
