{#
  Creates the raw tables in latam_raw from the column lists in
  models/staging/_sources.yml. Tables point at the original gzipped CSV files
  in the data-root bucket and read every column as STRING. A source can instead
  point at a Parquet copy with meta {format: parquet, location: ...}.

    dbt run-operation create_raw_tables                       # create missing tables
    dbt run-operation create_raw_tables --args '{replace: true}'  # drop and recreate all

  Uses the fh26-data-root bucket (override with DBT_RAW_BUCKET). Dropping a raw table only
  removes its definition; the files in S3 are never touched.
#}

{% macro create_raw_tables(replace=false) %}
  {% set bucket = env_var('DBT_RAW_BUCKET', 'fh26-data-root') %}

  {% for node in graph.sources.values() if node.source_name == 'latam_raw' %}
    {% set table = node.name %}
    {% set location = node.meta.get('location', 's3://' ~ bucket ~ '/' ~ table ~ '/') %}
    {% set partitioned = node.meta.get('partitioned', false) %}
    {% set is_parquet = node.meta.get('format') == 'parquet' %}

    {% if replace %}
      {% do run_query('DROP TABLE IF EXISTS latam_raw.`' ~ table ~ '`') %}
    {% endif %}

    {% set ddl %}
      CREATE EXTERNAL TABLE IF NOT EXISTS latam_raw.`{{ table }}` (
        {%- for col in node.columns.values() %}
        `{{ col.name }}` string{{ "," if not loop.last }}
        {%- endfor %}
      )
      {%- if partitioned %}
      PARTITIONED BY (`year` string, `month` string, `day` string)
      {%- endif %}
      {%- if is_parquet %}
      STORED AS PARQUET
      LOCATION '{{ location }}'
      {%- else %}
      ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
      WITH SERDEPROPERTIES ('separatorChar' = ',', 'quoteChar' = '"', 'escapeChar' = '\\')
      STORED AS TEXTFILE
      LOCATION '{{ location }}'
      TBLPROPERTIES (
        'skip.header.line.count' = '1'
        {%- if partitioned %},
        'projection.enabled' = 'true',
        'projection.year.type' = 'integer',
        'projection.year.range' = '2023,2026',
        'projection.month.type' = 'integer',
        'projection.month.range' = '1,12',
        'projection.month.digits' = '2',
        'projection.day.type' = 'integer',
        'projection.day.range' = '1,31',
        'projection.day.digits' = '2',
        'storage.location.template' = '{{ location }}year=${year}/month=${month}/day=${day}/'
        {%- endif %}
      )
      {%- endif %}
    {% endset %}

    {% do run_query(ddl) %}
    {% do log('raw table ready: latam_raw.' ~ table, info=true) %}
  {% endfor %}
{% endmacro %}
