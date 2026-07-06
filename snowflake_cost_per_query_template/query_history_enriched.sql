create schema dev.cost_per_query;

-- query_history_enriched
-- One row per query, enriched with allocated cost/credits (compute, cloud services,
-- query acceleration, Cortex functions) plus Sigma query-tag attribution.
-- Incrementally materialized nightly via Snowflake Task + Stored Procedure using MERGE.
-- (Cost-per-query calculation credit: Select.dev)
--
-- Configuration: replace the variables below before running.
--   materialization_role_name    : role used to create/own the table, procedure and task
--   target_database              : database where the table and task will be created
--   target_schema                : schema where the table and task will be created
--   sigma_role_name              : role used in your Sigma connection (granted SELECT on the table)
--   task_warehouse               : warehouse the procedure/task will use when it runs
--                                  (recommend a Medium warehouse unless query volumes are low)
--   task_refresh_cron            : CRON schedule for the nightly task
--
-- On first run this script will:
--   1. Set session variables, select the db/schema, and grant the materialization role
--      the privileges it needs
--   2. Create the table (if it doesn't exist)
--   3. Grant the Sigma service role SELECT on the table
--   4. Create (or replace) the stored procedure containing the transformation logic
--   5. Wrap the stored procedure in a task for nightly execution and resume it
--   6. Execute the stored procedure immediately to backfill the last 365 days

-- ------------------------------------------------------------
-- 1. Session variables, database/schema, and grants
-- ------------------------------------------------------------
SET materialization_role_name = 'name of role used while running this script';
SET target_database           = 'name of database where query_history_enriched will live';
SET target_schema             = 'name of schema where query_history_enriched will live';
SET sigma_role_name           = 'name of role used in Sigma connection that will read this table';
SET task_warehouse            = 'name of the warehouse you want to use';

-- Don't schedule earlier than 3am; there is some latency for Snowflake usage data.
SET task_refresh_cron         = 'USING CRON 0 3 * * Mon-Fri America/Los_Angeles';

USE database identifier($target_database);
USE schema identifier($target_schema);

-- Give the materialization role the privileges required to create the table, procedure and task.
USE role sysadmin;
GRANT imported privileges ON database snowflake TO role identifier($materialization_role_name);
GRANT create table       ON schema identifier($target_schema) TO role identifier($materialization_role_name);
GRANT create procedure   ON schema identifier($target_schema) TO role identifier($materialization_role_name);
GRANT create task        ON schema identifier($target_schema) TO role identifier($materialization_role_name);
GRANT execute task       ON account                           TO role identifier($materialization_role_name);

-- Now use the materialization role for everything that follows.
USE role identifier($materialization_role_name);
USE warehouse identifier($task_warehouse);

-- ------------------------------------------------------------
-- 2. Create the table
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS query_history_enriched (
    query_id                                    VARCHAR         NOT NULL    COMMENT 'Snowflake query ID (unique per query)',
    credits_attributed_compute                  FLOAT                       COMMENT 'Warehouse compute credits allocated to this query',
    compute_cost                                FLOAT                       COMMENT 'Cost of the allocated warehouse compute credits',
    credits_used_query_acceleration             FLOAT                       COMMENT 'Query acceleration service credits allocated to this query',
    query_acceleration_cost                     FLOAT                       COMMENT 'Cost of the allocated query acceleration credits',
    credits_used_cloud_services                 FLOAT                       COMMENT 'Cloud services credits allocated to this query (net of the daily 10% adjustment)',
    cloud_services_cost                         FLOAT                       COMMENT 'Cost of the allocated cloud services credits',
    cortex_functions_cost                       FLOAT                       COMMENT 'Cost of Cortex (AI) function credits consumed by this query',
    credits_used_cortex_functions               FLOAT                       COMMENT 'Cortex (AI) function credits consumed by this query',
    total_cost                                  FLOAT                       COMMENT 'Total allocated cost: compute + query acceleration + cloud services + Cortex',
    query_text                                  VARCHAR                     COMMENT 'Text of the SQL statement',
    database_id                                 NUMBER                      COMMENT 'ID of the database used in the query',
    database_name                               VARCHAR                     COMMENT 'Database used in the query',
    schema_id                                   NUMBER                      COMMENT 'ID of the schema used in the query',
    schema_name                                 VARCHAR                     COMMENT 'Schema used in the query',
    query_type                                  VARCHAR                     COMMENT 'Type of the query (SELECT, INSERT, etc)',
    session_id                                  NUMBER                      COMMENT 'Session that issued the query',
    user_name                                   VARCHAR                     COMMENT 'Snowflake user who executed the query',
    role_name                                   VARCHAR                     COMMENT 'Snowflake role used to execute the query',
    warehouse_id                                NUMBER                      COMMENT 'ID of the warehouse the query ran on',
    warehouse_name                              VARCHAR                     COMMENT 'Warehouse the query ran on',
    warehouse_size                              VARCHAR                     COMMENT 'Size of the warehouse the query ran on',
    warehouse_type                              VARCHAR                     COMMENT 'Type of the warehouse the query ran on',
    cluster_number                              NUMBER                      COMMENT 'Cluster (within a multi-cluster warehouse) the query ran on',
    is_metadata_query                           BOOLEAN                     COMMENT 'True if the query text starts with SHOW or DESC',
    is_select_query                             BOOLEAN                     COMMENT 'True if the query is a SELECT (and not a view DDL)',
    query_tag                                   VARCHAR                     COMMENT 'The complete query tag sent to Snowflake',
    is_sigma_query                              BOOLEAN                     COMMENT 'True if query was executed by Sigma',
    sigma_query_tag_json                        VARIANT                     COMMENT 'Parsed Sigma query tag JSON',
    sigma_query_kind                            VARCHAR                     COMMENT 'The kind of the Sigma query',
    sigma_source_url                            VARCHAR                     COMMENT 'Sigma document or element where the query originated',
    sigma_request_id                            VARCHAR                     COMMENT 'Sigma request ID',
    sigma_user_email                            VARCHAR                     COMMENT 'Sigma user who executed the query',
    sigma_user_email_domain                     VARCHAR                     COMMENT 'Domain portion of the Sigma user email',
    sigma_document_url                          VARCHAR                     COMMENT 'Sigma document URL (source URL with query string removed)',
    sigma_document_name                         VARCHAR                     COMMENT 'Sigma document name where the query originated',
    execution_status                            VARCHAR                     COMMENT 'Execution status (success, fail, incident)',
    error_code                                  VARCHAR                     COMMENT 'Error code, if the query returned an error',
    error_message                               VARCHAR                     COMMENT 'Error message, if the query returned an error',
    start_time                                  TIMESTAMP_LTZ               COMMENT 'Statement start time',
    end_time                                    TIMESTAMP_LTZ               COMMENT 'Statement end time',
    ran_on_warehouse                            BOOLEAN                     COMMENT 'True if the query ran on a warehouse',
    total_elapsed_time_ms                       NUMBER                      COMMENT 'Elapsed time (ms)',
    compilation_time_ms                         NUMBER                      COMMENT 'Compilation time (ms)',
    queued_provisioning_time_ms                 NUMBER                      COMMENT 'Time spent waiting for warehouse provisioning (ms)',
    queued_repair_time_ms                       NUMBER                      COMMENT 'Time spent waiting for warehouse repair (ms)',
    queued_overload_time_ms                     NUMBER                      COMMENT 'Time spent queued due to warehouse overload (ms)',
    transaction_blocked_time_ms                 NUMBER                      COMMENT 'Time blocked by a concurrent transaction (ms)',
    list_external_files_time_ms                 NUMBER                      COMMENT 'Time spent listing external files (ms)',
    execution_time_ms                           NUMBER                      COMMENT 'Execution time (ms)',
    bytes_scanned                               NUMBER                      COMMENT 'Bytes scanned by the query',
    percentage_scanned_from_cache               FLOAT                       COMMENT 'Percentage of scanned data read from the local cache',
    bytes_written                               NUMBER                      COMMENT 'Bytes written by the query',
    bytes_written_to_result                     NUMBER                      COMMENT 'Bytes written to the result object',
    bytes_read_from_result                      NUMBER                      COMMENT 'Bytes read from the result object',
    rows_produced                               NUMBER                      COMMENT 'Rows produced by the query',
    rows_inserted                               NUMBER                      COMMENT 'Rows inserted by the query',
    rows_updated                                NUMBER                      COMMENT 'Rows updated by the query',
    rows_deleted                                NUMBER                      COMMENT 'Rows deleted by the query',
    rows_unloaded                               NUMBER                      COMMENT 'Rows unloaded during data export',
    bytes_deleted                               NUMBER                      COMMENT 'Bytes deleted by the query',
    partitions_scanned                          NUMBER                      COMMENT 'Micro-partitions scanned',
    partitions_total                            NUMBER                      COMMENT 'Total micro-partitions in the scanned objects',
    bytes_spilled_to_local_storage              NUMBER                      COMMENT 'Bytes spilled to local disk',
    bytes_spilled_to_remote_storage             NUMBER                      COMMENT 'Bytes spilled to remote storage',
    bytes_sent_over_the_network                 NUMBER                      COMMENT 'Bytes sent over the network',
    outbound_data_transfer_cloud                VARCHAR                     COMMENT 'Target cloud for outbound data transfer',
    outbound_data_transfer_region               VARCHAR                     COMMENT 'Target region for outbound data transfer',
    outbound_data_transfer_bytes                NUMBER                      COMMENT 'Bytes transferred outbound',
    inbound_data_transfer_cloud                 VARCHAR                     COMMENT 'Source cloud for inbound data transfer',
    inbound_data_transfer_region                VARCHAR                     COMMENT 'Source region for inbound data transfer',
    inbound_data_transfer_bytes                 NUMBER                      COMMENT 'Bytes transferred inbound',
    release_version                             VARCHAR                     COMMENT 'Snowflake release version at execution time',
    external_function_total_invocations         NUMBER                      COMMENT 'Total external function invocations',
    external_function_total_sent_rows           NUMBER                      COMMENT 'Total rows sent to external functions',
    external_function_total_received_rows       NUMBER                      COMMENT 'Total rows received from external functions',
    external_function_total_sent_bytes          NUMBER                      COMMENT 'Total bytes sent to external functions',
    external_function_total_received_bytes      NUMBER                      COMMENT 'Total bytes received from external functions',
    query_load_percent                          FLOAT                       COMMENT 'Approximate percentage of warehouse resources used by the query',
    is_client_generated_statement               BOOLEAN                     COMMENT 'True if the statement was generated by the client',
    query_acceleration_bytes_scanned            NUMBER                      COMMENT 'Bytes scanned by the query acceleration service',
    query_acceleration_partitions_scanned       NUMBER                      COMMENT 'Partitions scanned by the query acceleration service',
    query_acceleration_upper_limit_scale_factor NUMBER                      COMMENT 'Upper-limit scale factor for query acceleration',
    parent_query_id                             VARCHAR                     COMMENT 'Query ID of the direct parent job',
    root_query_id                               VARCHAR                     COMMENT 'Query ID of the root job in the job tree',
    cortex_credits_by_function                  VARIANT                     COMMENT 'Object mapping Cortex function name -> credits consumed',
    cortex_usage_details                        VARIANT                     COMMENT 'Array of per-invocation Cortex usage details (model, function, tokens, credits)'
)
CLUSTER BY (to_date(start_time));

-- ------------------------------------------------------------
-- 3. Grant the Sigma service role SELECT on the table
-- ------------------------------------------------------------
GRANT usage  ON database identifier($target_database) TO role identifier($sigma_role_name);
GRANT usage  ON schema   identifier($target_schema)   TO role identifier($sigma_role_name);
GRANT select ON table    query_history_enriched       TO role identifier($sigma_role_name);

-- ------------------------------------------------------------
-- 4. Stored procedure that contains the MERGE logic
-- ------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_query_history_enriched_refresh(lookback_days FLOAT)
RETURNS STRING
LANGUAGE SQL
AS
BEGIN
    MERGE INTO query_history_enriched AS target
    USING (
        with query_history as (
            select
                *
            from snowflake.account_usage.query_history
            where end_time < date_trunc(day, getdate())
              and start_time >= DATEADD('day', -:lookback_days, current_timestamp())
        )

        , dates_base as (
            select date_day as date from (
                with rawdata as (
                    with p as (
                        select 0 as generated_number union all select 1
                    ),
                    unioned as (
                        select
                        p0.generated_number * power(2, 0)
                        +
                        p1.generated_number * power(2, 1)
                        +
                        p2.generated_number * power(2, 2)
                        +
                        p3.generated_number * power(2, 3)
                        +
                        p4.generated_number * power(2, 4)
                        +
                        p5.generated_number * power(2, 5)
                        +
                        p6.generated_number * power(2, 6)
                        +
                        p7.generated_number * power(2, 7)
                        +
                        p8.generated_number * power(2, 8)
                        +
                        p9.generated_number * power(2, 9)
                        +
                        p10.generated_number * power(2, 10)
                        +
                        p11.generated_number * power(2, 11)
                        +
                        p12.generated_number * power(2, 12)
                        + 1
                        as generated_number
                        from
                        p as p0
                        cross join
                        p as p1
                        cross join
                        p as p2
                        cross join
                        p as p3
                        cross join
                        p as p4
                        cross join
                        p as p5
                        cross join
                        p as p6
                        cross join
                        p as p7
                        cross join
                        p as p8
                        cross join
                        p as p9
                        cross join
                        p as p10
                        cross join
                        p as p11
                        cross join
                        p as p12
                    )
                    select *
                    from unioned
                    where generated_number <= 10000
                    order by generated_number
                ),

                all_periods as (

                    select (
                    dateadd(
                        day,
                        row_number() over (order by 1) - 1,
                        '2018-01-01'
                        )
                    ) as date_day
                    from rawdata

                ),

                filtered as (
                    select *
                    from all_periods
                    where date_day <= dateadd(day, 1, current_date)
                )

                select * from filtered


            )
        )

        , rate_sheet_daily_base as (
            select
                date,
                usage_type,
                currency,
                effective_rate,
                service_type
            from snowflake.organization_usage.rate_sheet_daily
            where
                account_locator = current_account()
        )

        , remaining_balance_daily_without_contract_view as (
            select
                date,
                organization_name,
                currency,
                free_usage_balance,
                capacity_balance,
                on_demand_consumption_balance,
                rollover_balance
            from snowflake.organization_usage.remaining_balance_daily

            qualify row_number() over (partition by date order by contract_number desc) = 1
        )

        , stop_thresholds as (
            select min(date) as start_date
            from rate_sheet_daily_base

            union all

            select min(date) as start_date
            from remaining_balance_daily_without_contract_view
        )

        , date_range as (
            select
                max(start_date) as start_date,
                current_date as end_date
            from stop_thresholds
        )

        , remaining_balance_daily as (
            select
                date,
                free_usage_balance + capacity_balance + on_demand_consumption_balance + rollover_balance as remaining_balance,
                remaining_balance < 0 as is_account_in_overage
            from remaining_balance_daily_without_contract_view
        )

        , latest_remaining_balance_daily as (
            select
                date,
                remaining_balance,
                is_account_in_overage
            from remaining_balance_daily
            qualify row_number() over (order by date desc) = 1
        )

        , rate_sheet_daily as (
            select rate_sheet_daily_base.*
            from rate_sheet_daily_base
            inner join date_range
                on rate_sheet_daily_base.date between date_range.start_date and date_range.end_date
        )

        , rates_date_range_w_usage_types as (
            select
                date_range.start_date,
                date_range.end_date,
                usage_types.usage_type
            from date_range
            cross join (select distinct usage_type from rate_sheet_daily) as usage_types
        )

        , base as (
            select
                db.date,
                dr.usage_type
            from dates_base as db
            inner join rates_date_range_w_usage_types as dr
                on db.date between dr.start_date and dr.end_date
        )

        , rates_w_overage as (
            select
                base.date,
                base.usage_type,
                coalesce(
                    rate_sheet_daily.service_type,
                    lag(rate_sheet_daily.service_type) ignore nulls over (partition by base.usage_type order by base.date),
                    lead(rate_sheet_daily.service_type) ignore nulls over (partition by base.usage_type order by base.date)
                ) as service_type,
                coalesce(
                    rate_sheet_daily.effective_rate,
                    lag(rate_sheet_daily.effective_rate) ignore nulls over (partition by base.usage_type order by base.date),
                    lead(rate_sheet_daily.effective_rate) ignore nulls over (partition by base.usage_type order by base.date)
                ) as effective_rate,
                coalesce(
                    rate_sheet_daily.currency,
                    lag(rate_sheet_daily.currency) ignore nulls over (partition by base.usage_type order by base.date),
                    lead(rate_sheet_daily.currency) ignore nulls over (partition by base.usage_type order by base.date)
                ) as currency,
                base.usage_type like 'overage-%' as is_overage_rate,
                replace(base.usage_type, 'overage-', '') as associated_usage_type,
                coalesce(remaining_balance_daily.is_account_in_overage, latest_remaining_balance_daily.is_account_in_overage, false) as _is_account_in_overage,
                case
                    when _is_account_in_overage and is_overage_rate then 1
                    when not _is_account_in_overage and not is_overage_rate then 1
                    else 0
                end as rate_priority

            from base
            left join latest_remaining_balance_daily on latest_remaining_balance_daily.date is not null
            left join remaining_balance_daily
                on base.date = remaining_balance_daily.date
            left join rate_sheet_daily
                on base.date = rate_sheet_daily.date
                    and base.usage_type = rate_sheet_daily.usage_type
        )

        , rates as (
            select
                date,
                usage_type,
                associated_usage_type,
                service_type,
                effective_rate,
                currency,
                is_overage_rate
            from rates_w_overage
            qualify row_number() over (partition by date, service_type, associated_usage_type order by rate_priority desc) = 1
        )

        , daily_rates as (
            select
                date,
                associated_usage_type as usage_type,
                service_type,
                effective_rate,
                currency,
                is_overage_rate,
                row_number() over (partition by service_type, associated_usage_type order by date desc) = 1 as is_latest_rate
            from rates
            order by date
        )

        , stop_threshold as (
            select max(end_time) as latest_ts
            from snowflake.account_usage.warehouse_metering_history
        )

        , filtered_queries as (
            select
                query_id,
                query_text as original_query_text,
                credits_used_cloud_services,
                warehouse_id,
                warehouse_size is not null as ran_on_warehouse,
                timeadd(
                    'millisecond',
                    queued_overload_time + compilation_time
                    + queued_provisioning_time + queued_repair_time
                    + list_external_files_time,
                    start_time
                ) as execution_start_time,
                start_time,
                end_time,
                query_acceleration_bytes_scanned
            from snowflake.account_usage.query_history
            where end_time <= (select latest_ts from stop_threshold)
            and end_time < date_trunc(day, getdate())
            and start_time >= DATEADD('day', -:lookback_days, current_timestamp())
        )

        , hours_list as (
            select
                dateadd(
                    'hour',
                    '-' || row_number() over (order by seq4() asc),
                    dateadd('day', '+1', current_date::timestamp_tz)
                ) as hour_start,
                dateadd('hour', '+1', hour_start) as hour_end
            from table(generator(rowcount => (24 * 730)))
        )

        , query_hours as (
            select
                hours_list.hour_start,
                hours_list.hour_end,
                queries.*
            from hours_list
            inner join filtered_queries as queries
                on hours_list.hour_start >= date_trunc('hour', queries.execution_start_time)
                    and hours_list.hour_start < queries.end_time
                    and queries.ran_on_warehouse
        )

        , query_seconds_per_hour as (
            select
                *,
                datediff('millisecond', greatest(execution_start_time, hour_start), least(end_time, hour_end)) as num_milliseconds_query_ran,
                sum(num_milliseconds_query_ran) over (partition by warehouse_id, hour_start) as total_query_milliseconds_in_hour,
                div0(num_milliseconds_query_ran, total_query_milliseconds_in_hour) as fraction_of_total_query_time_in_hour,
                sum(query_acceleration_bytes_scanned) over (partition by warehouse_id, hour_start) as total_query_acceleration_bytes_scanned_in_hour,
                div0(query_acceleration_bytes_scanned, total_query_acceleration_bytes_scanned_in_hour) as fraction_of_total_query_acceleration_bytes_scanned_in_hour,
                hour_start as hour
            from query_hours
        )

        , credits_billed_hourly as (
            select
                start_time as hour,
                entity_id as warehouse_id,
                sum(iff(service_type = 'WAREHOUSE_METERING', credits_used_compute, 0)) as credits_used_compute,
                sum(iff(service_type = 'WAREHOUSE_METERING', credits_used_cloud_services, 0)) as credits_used_cloud_services,
                sum(iff(service_type = 'QUERY_ACCELERATION', credits_used_compute, 0)) as credits_used_query_acceleration
            from snowflake.account_usage.metering_history
            where true
                and service_type in ('QUERY_ACCELERATION', 'WAREHOUSE_METERING')
            group by 1, 2
        )

        , query_cost as (
            select
                query_seconds_per_hour.*,
                credits_billed_hourly.credits_used_compute * daily_rates.effective_rate as actual_warehouse_cost,
                credits_billed_hourly.credits_used_compute * query_seconds_per_hour.fraction_of_total_query_time_in_hour * daily_rates.effective_rate as allocated_compute_cost_in_hour,
                credits_billed_hourly.credits_used_compute * query_seconds_per_hour.fraction_of_total_query_time_in_hour as allocated_compute_credits_in_hour,
                credits_billed_hourly.credits_used_query_acceleration * query_seconds_per_hour.fraction_of_total_query_acceleration_bytes_scanned_in_hour as allocated_query_acceleration_credits_in_hour,
                allocated_query_acceleration_credits_in_hour * daily_rates.effective_rate as allocated_query_acceleration_cost_in_hour
            from query_seconds_per_hour
            inner join credits_billed_hourly
                on query_seconds_per_hour.warehouse_id = credits_billed_hourly.warehouse_id
                    and query_seconds_per_hour.hour = credits_billed_hourly.hour
            inner join daily_rates
                on date(query_seconds_per_hour.start_time) = daily_rates.date
                    and daily_rates.service_type = 'WAREHOUSE_METERING'
                    and daily_rates.usage_type = 'compute'
        )

        , cost_per_query as (
            select
                query_id,
                any_value(start_time) as start_time,
                any_value(end_time) as end_time,
                any_value(execution_start_time) as execution_start_time,
                sum(allocated_compute_cost_in_hour) as compute_cost,
                sum(allocated_compute_credits_in_hour) as compute_credits,
                sum(allocated_query_acceleration_cost_in_hour) as query_acceleration_cost,
                sum(allocated_query_acceleration_credits_in_hour) as query_acceleration_credits,
                any_value(credits_used_cloud_services) as credits_used_cloud_services,
                any_value(ran_on_warehouse) as ran_on_warehouse
            from query_cost
            group by 1
        )

        , credits_billed_daily as (
            select
                date(hour) as date,
                sum(credits_used_compute) as daily_credits_used_compute,
                sum(credits_used_cloud_services) as daily_credits_used_cloud_services,
                greatest(daily_credits_used_cloud_services - daily_credits_used_compute * 0.1, 0) as daily_billable_cloud_services
            from credits_billed_hourly
            group by 1
        )

        , all_queries as (
            select
                query_id,
                start_time,
                end_time,
                execution_start_time,
                compute_cost,
                compute_credits,
                query_acceleration_cost,
                query_acceleration_credits,
                credits_used_cloud_services,
                ran_on_warehouse
            from cost_per_query

            union all

            select
                query_id,
                start_time,
                end_time,
                execution_start_time,
                0 as compute_cost,
                0 as compute_credits,
                0 as query_acceleration_cost,
                0 as query_acceleration_credits,
                credits_used_cloud_services,
                ran_on_warehouse
            from filtered_queries
            where
                not ran_on_warehouse
        )

        , cortex_consumption_by_function as (
            select query_id
            , function_name
            , sum(token_credits) as credits
            from snowflake.account_usage.cortex_functions_query_usage_history
            group by query_id, function_name
        )

        , cortex_function_usage_details as (
            select query_id
            , sum(token_credits) as credits
            , array_agg(object_construct('model_name', model_name, 'function_name', function_name, 'tokens', tokens, 'token_credits', token_credits)) as details
            from snowflake.account_usage.cortex_functions_query_usage_history
            group by query_id
        )

        , cortex_function_usage_by_query as (
            select query_id
            , object_agg(function_name, credits) as function_credits
            from cortex_consumption_by_function
            group by query_id
        )

        , cortex_function_cost_and_usage_by_query as (
            select cortex_function_usage_details.query_id
            , cortex_function_usage_details.credits as cortex_credits
            , cortex_function_usage_by_query.function_credits as cortex_credits_by_function
            , cortex_function_usage_details.details as cortex_usage_details
            from cortex_function_usage_details
            left join cortex_function_usage_by_query
                on cortex_function_usage_by_query.query_id = cortex_function_usage_details.query_id
        )

        , stg__cost_per_query as (
            select
                all_queries.query_id,
                all_queries.start_time,
                all_queries.end_time,
                all_queries.execution_start_time,
                all_queries.compute_cost,
                all_queries.compute_credits,
                all_queries.query_acceleration_cost,
                all_queries.query_acceleration_credits,
                -- For the most recent day, which is not yet complete, this calculation won't be perfect.
                -- So, we don't look at any queries from the most recent day t, just t-1 and before.
                (div0(all_queries.credits_used_cloud_services, credits_billed_daily.daily_credits_used_cloud_services) * credits_billed_daily.daily_billable_cloud_services) * coalesce(daily_rates.effective_rate, current_rates.effective_rate) as cloud_services_cost,
                div0(all_queries.credits_used_cloud_services, credits_billed_daily.daily_credits_used_cloud_services) * credits_billed_daily.daily_billable_cloud_services as cloud_services_credits,
                zeroifnull(cortex_function_cost_and_usage_by_query.cortex_credits * coalesce(ai_services_daily_rates.effective_rate, ai_services_current_rates.effective_rate)) as cortex_functions_cost,
                zeroifnull(cortex_function_cost_and_usage_by_query.cortex_credits) as cortex_functions_credits,
                all_queries.compute_cost + all_queries.query_acceleration_cost + cloud_services_cost + cortex_functions_cost as query_cost,
                all_queries.compute_credits + all_queries.query_acceleration_credits + cloud_services_credits + cortex_functions_credits as query_credits,
                all_queries.ran_on_warehouse,
                coalesce(daily_rates.currency, current_rates.currency) as currency
            from all_queries
            inner join credits_billed_daily
                on date(all_queries.start_time) = credits_billed_daily.date
            left join daily_rates
                on date(all_queries.start_time) = daily_rates.date
                    and daily_rates.service_type = 'CLOUD_SERVICES'
                    and daily_rates.usage_type = 'cloud services'
            inner join daily_rates as current_rates
                on current_rates.is_latest_rate
                    and current_rates.service_type = 'CLOUD_SERVICES'
                    and current_rates.usage_type = 'cloud services'
            left join daily_rates as ai_services_daily_rates
                on date(all_queries.start_time) = ai_services_daily_rates.date
                    and ai_services_daily_rates.service_type = 'AI_SERVICES'
                    and ai_services_daily_rates.usage_type = 'ai services'
            inner join daily_rates as ai_services_current_rates
                on ai_services_current_rates.is_latest_rate
                    and ai_services_current_rates.service_type = 'AI_SERVICES'
                    and ai_services_current_rates.usage_type = 'ai services'
            left join cortex_function_cost_and_usage_by_query
                on all_queries.query_id = cortex_function_cost_and_usage_by_query.query_id
            order by all_queries.start_time asc
        )

        , query_attribution_history as (
            select *
            from snowflake.account_usage.query_attribution_history
            where end_time < date_trunc(day, getdate())
            and start_time >= DATEADD('day', -:lookback_days, current_timestamp())
        )

        , final as (
            select query_history.query_id
            , cost_per_query.compute_credits as credits_attributed_compute
            , cost_per_query.compute_cost as compute_cost
            , cost_per_query.query_acceleration_credits as credits_used_query_acceleration
            , cost_per_query.query_acceleration_cost as query_acceleration_cost
            , cost_per_query.cloud_services_credits as credits_used_cloud_services
            , cost_per_query.cloud_services_cost as cloud_services_cost
            , cost_per_query.cortex_functions_cost as cortex_functions_cost
            , cost_per_query.cortex_functions_credits as credits_used_cortex_functions
            , cost_per_query.query_cost as total_cost
            , query_history.query_text
            , query_history.database_id
            , query_history.database_name
            , query_history.schema_id
            , query_history.schema_name
            , query_history.query_type
            , query_history.session_id
            , query_history.user_name
            , query_history.role_name
            , query_history.warehouse_id
            , query_history.warehouse_name
            , query_history.warehouse_size
            , query_history.warehouse_type
            , query_history.cluster_number
            , regexp_like(lower(query_text), '^(show|desc)') as is_metadata_query
            , (regexp_like(lower(query_text), 'select(.|\n|\r)*from(.|\n|\r)*') or regexp_like(lower(query_text), '^with.*select.*from.*')) and not(regexp_like(lower(query_text), '^create(.|\n|\r)*(or replace|secure|recursive)?(.|\n|\r)*view')) as is_select_query
            , query_history.query_tag
            , contains(query_history.query_tag, 'Sigma Σ') as is_sigma_query
            , try_parse_json(regexp_replace(query_history.query_tag, 'Sigma Σ ', '')) as sigma_query_tag_json
            , sigma_query_tag_json:kind::text as sigma_query_kind
            , sigma_query_tag_json:sourceUrl::text as sigma_source_url
            , sigma_query_tag_json:"request-id"::text as sigma_request_id
            , sigma_query_tag_json:email::text as sigma_user_email
            , split_part(split_part(sigma_user_email, '@', 2), '.', 1) as sigma_user_email_domain
            , split_part(sigma_source_url, '?', 1) as sigma_document_url
            , trim(regexp_replace(regexp_replace(split_part(split_part(sigma_source_url, '/', 6), '?:', 1), right(split_part(split_part(sigma_source_url, '/', 6), '?:', 1), 22), ''), '-', ' ')) as sigma_document_name
            , query_history.execution_status
            , query_history.error_code
            , query_history.error_message
            , query_history.start_time
            , query_history.end_time
            , query_history.warehouse_size is not null as ran_on_warehouse
            , query_history.total_elapsed_time as total_elapsed_time_ms
            , query_history.compilation_time as compilation_time_ms
            , query_history.queued_provisioning_time as queued_provisioning_time_ms
            , query_history.queued_repair_time as queued_repair_time_ms
            , query_history.queued_overload_time as queued_overload_time_ms
            , query_history.transaction_blocked_time as transaction_blocked_time_ms
            , query_history.list_external_files_time as list_external_files_time_ms
            , query_history.execution_time as execution_time_ms
            , query_history.bytes_scanned
            , query_history.percentage_scanned_from_cache
            , query_history.bytes_written
            , query_history.bytes_written_to_result
            , query_history.bytes_read_from_result
            , query_history.rows_produced
            , query_history.rows_inserted
            , query_history.rows_updated
            , query_history.rows_deleted
            , query_history.rows_unloaded
            , query_history.bytes_deleted
            , query_history.partitions_scanned
            , query_history.partitions_total
            , query_history.bytes_spilled_to_local_storage
            , query_history.bytes_spilled_to_remote_storage
            , query_history.bytes_sent_over_the_network
            , query_history.outbound_data_transfer_cloud
            , query_history.outbound_data_transfer_region
            , query_history.outbound_data_transfer_bytes
            , query_history.inbound_data_transfer_cloud
            , query_history.inbound_data_transfer_region
            , query_history.inbound_data_transfer_bytes
            , query_history.release_version
            , query_history.external_function_total_invocations
            , query_history.external_function_total_sent_rows
            , query_history.external_function_total_received_rows
            , query_history.external_function_total_sent_bytes
            , query_history.external_function_total_received_bytes
            , query_history.query_load_percent
            , query_history.is_client_generated_statement
            , query_history.query_acceleration_bytes_scanned
            , query_history.query_acceleration_partitions_scanned
            , query_history.query_acceleration_upper_limit_scale_factor
            , query_attribution_history.parent_query_id
            , query_attribution_history.root_query_id
            , cortex_function_cost_and_usage_by_query.cortex_credits_by_function
            , cortex_function_cost_and_usage_by_query.cortex_usage_details
            from query_history
            left join stg__cost_per_query cost_per_query
                on query_history.query_id = cost_per_query.query_id
            left join query_attribution_history
                on query_attribution_history.query_id = query_history.query_id
            left join cortex_function_cost_and_usage_by_query
                on cortex_function_cost_and_usage_by_query.query_id = query_history.query_id
        )

        select *
        from final

    ) AS source
    ON target.query_id = source.query_id

    WHEN MATCHED THEN UPDATE SET
        target.credits_attributed_compute                  = source.credits_attributed_compute
        , target.compute_cost                              = source.compute_cost
        , target.credits_used_query_acceleration           = source.credits_used_query_acceleration
        , target.query_acceleration_cost                   = source.query_acceleration_cost
        , target.credits_used_cloud_services               = source.credits_used_cloud_services
        , target.cloud_services_cost                       = source.cloud_services_cost
        , target.cortex_functions_cost                     = source.cortex_functions_cost
        , target.credits_used_cortex_functions             = source.credits_used_cortex_functions
        , target.total_cost                                = source.total_cost
        , target.query_text                                = source.query_text
        , target.database_id                               = source.database_id
        , target.database_name                             = source.database_name
        , target.schema_id                                 = source.schema_id
        , target.schema_name                               = source.schema_name
        , target.query_type                                = source.query_type
        , target.session_id                                = source.session_id
        , target.user_name                                 = source.user_name
        , target.role_name                                 = source.role_name
        , target.warehouse_id                              = source.warehouse_id
        , target.warehouse_name                            = source.warehouse_name
        , target.warehouse_size                            = source.warehouse_size
        , target.warehouse_type                            = source.warehouse_type
        , target.cluster_number                            = source.cluster_number
        , target.is_metadata_query                         = source.is_metadata_query
        , target.is_select_query                           = source.is_select_query
        , target.query_tag                                 = source.query_tag
        , target.is_sigma_query                            = source.is_sigma_query
        , target.sigma_query_tag_json                      = source.sigma_query_tag_json
        , target.sigma_query_kind                          = source.sigma_query_kind
        , target.sigma_source_url                          = source.sigma_source_url
        , target.sigma_request_id                          = source.sigma_request_id
        , target.sigma_user_email                          = source.sigma_user_email
        , target.sigma_user_email_domain                   = source.sigma_user_email_domain
        , target.sigma_document_url                        = source.sigma_document_url
        , target.sigma_document_name                       = source.sigma_document_name
        , target.execution_status                          = source.execution_status
        , target.error_code                                = source.error_code
        , target.error_message                             = source.error_message
        , target.start_time                                = source.start_time
        , target.end_time                                  = source.end_time
        , target.ran_on_warehouse                          = source.ran_on_warehouse
        , target.total_elapsed_time_ms                     = source.total_elapsed_time_ms
        , target.compilation_time_ms                       = source.compilation_time_ms
        , target.queued_provisioning_time_ms               = source.queued_provisioning_time_ms
        , target.queued_repair_time_ms                     = source.queued_repair_time_ms
        , target.queued_overload_time_ms                   = source.queued_overload_time_ms
        , target.transaction_blocked_time_ms               = source.transaction_blocked_time_ms
        , target.list_external_files_time_ms               = source.list_external_files_time_ms
        , target.execution_time_ms                         = source.execution_time_ms
        , target.bytes_scanned                             = source.bytes_scanned
        , target.percentage_scanned_from_cache             = source.percentage_scanned_from_cache
        , target.bytes_written                             = source.bytes_written
        , target.bytes_written_to_result                   = source.bytes_written_to_result
        , target.bytes_read_from_result                    = source.bytes_read_from_result
        , target.rows_produced                             = source.rows_produced
        , target.rows_inserted                             = source.rows_inserted
        , target.rows_updated                              = source.rows_updated
        , target.rows_deleted                              = source.rows_deleted
        , target.rows_unloaded                             = source.rows_unloaded
        , target.bytes_deleted                             = source.bytes_deleted
        , target.partitions_scanned                        = source.partitions_scanned
        , target.partitions_total                          = source.partitions_total
        , target.bytes_spilled_to_local_storage            = source.bytes_spilled_to_local_storage
        , target.bytes_spilled_to_remote_storage           = source.bytes_spilled_to_remote_storage
        , target.bytes_sent_over_the_network               = source.bytes_sent_over_the_network
        , target.outbound_data_transfer_cloud              = source.outbound_data_transfer_cloud
        , target.outbound_data_transfer_region             = source.outbound_data_transfer_region
        , target.outbound_data_transfer_bytes              = source.outbound_data_transfer_bytes
        , target.inbound_data_transfer_cloud               = source.inbound_data_transfer_cloud
        , target.inbound_data_transfer_region              = source.inbound_data_transfer_region
        , target.inbound_data_transfer_bytes               = source.inbound_data_transfer_bytes
        , target.release_version                           = source.release_version
        , target.external_function_total_invocations       = source.external_function_total_invocations
        , target.external_function_total_sent_rows         = source.external_function_total_sent_rows
        , target.external_function_total_received_rows     = source.external_function_total_received_rows
        , target.external_function_total_sent_bytes        = source.external_function_total_sent_bytes
        , target.external_function_total_received_bytes    = source.external_function_total_received_bytes
        , target.query_load_percent                        = source.query_load_percent
        , target.is_client_generated_statement             = source.is_client_generated_statement
        , target.query_acceleration_bytes_scanned          = source.query_acceleration_bytes_scanned
        , target.query_acceleration_partitions_scanned     = source.query_acceleration_partitions_scanned
        , target.query_acceleration_upper_limit_scale_factor = source.query_acceleration_upper_limit_scale_factor
        , target.parent_query_id                           = source.parent_query_id
        , target.root_query_id                             = source.root_query_id
        , target.cortex_credits_by_function                = source.cortex_credits_by_function
        , target.cortex_usage_details                      = source.cortex_usage_details

    WHEN NOT MATCHED THEN INSERT (
        query_id
        , credits_attributed_compute
        , compute_cost
        , credits_used_query_acceleration
        , query_acceleration_cost
        , credits_used_cloud_services
        , cloud_services_cost
        , cortex_functions_cost
        , credits_used_cortex_functions
        , total_cost
        , query_text
        , database_id
        , database_name
        , schema_id
        , schema_name
        , query_type
        , session_id
        , user_name
        , role_name
        , warehouse_id
        , warehouse_name
        , warehouse_size
        , warehouse_type
        , cluster_number
        , is_metadata_query
        , is_select_query
        , query_tag
        , is_sigma_query
        , sigma_query_tag_json
        , sigma_query_kind
        , sigma_source_url
        , sigma_request_id
        , sigma_user_email
        , sigma_user_email_domain
        , sigma_document_url
        , sigma_document_name
        , execution_status
        , error_code
        , error_message
        , start_time
        , end_time
        , ran_on_warehouse
        , total_elapsed_time_ms
        , compilation_time_ms
        , queued_provisioning_time_ms
        , queued_repair_time_ms
        , queued_overload_time_ms
        , transaction_blocked_time_ms
        , list_external_files_time_ms
        , execution_time_ms
        , bytes_scanned
        , percentage_scanned_from_cache
        , bytes_written
        , bytes_written_to_result
        , bytes_read_from_result
        , rows_produced
        , rows_inserted
        , rows_updated
        , rows_deleted
        , rows_unloaded
        , bytes_deleted
        , partitions_scanned
        , partitions_total
        , bytes_spilled_to_local_storage
        , bytes_spilled_to_remote_storage
        , bytes_sent_over_the_network
        , outbound_data_transfer_cloud
        , outbound_data_transfer_region
        , outbound_data_transfer_bytes
        , inbound_data_transfer_cloud
        , inbound_data_transfer_region
        , inbound_data_transfer_bytes
        , release_version
        , external_function_total_invocations
        , external_function_total_sent_rows
        , external_function_total_received_rows
        , external_function_total_sent_bytes
        , external_function_total_received_bytes
        , query_load_percent
        , is_client_generated_statement
        , query_acceleration_bytes_scanned
        , query_acceleration_partitions_scanned
        , query_acceleration_upper_limit_scale_factor
        , parent_query_id
        , root_query_id
        , cortex_credits_by_function
        , cortex_usage_details
    )
    VALUES (
        source.query_id
        , source.credits_attributed_compute
        , source.compute_cost
        , source.credits_used_query_acceleration
        , source.query_acceleration_cost
        , source.credits_used_cloud_services
        , source.cloud_services_cost
        , source.cortex_functions_cost
        , source.credits_used_cortex_functions
        , source.total_cost
        , source.query_text
        , source.database_id
        , source.database_name
        , source.schema_id
        , source.schema_name
        , source.query_type
        , source.session_id
        , source.user_name
        , source.role_name
        , source.warehouse_id
        , source.warehouse_name
        , source.warehouse_size
        , source.warehouse_type
        , source.cluster_number
        , source.is_metadata_query
        , source.is_select_query
        , source.query_tag
        , source.is_sigma_query
        , source.sigma_query_tag_json
        , source.sigma_query_kind
        , source.sigma_source_url
        , source.sigma_request_id
        , source.sigma_user_email
        , source.sigma_user_email_domain
        , source.sigma_document_url
        , source.sigma_document_name
        , source.execution_status
        , source.error_code
        , source.error_message
        , source.start_time
        , source.end_time
        , source.ran_on_warehouse
        , source.total_elapsed_time_ms
        , source.compilation_time_ms
        , source.queued_provisioning_time_ms
        , source.queued_repair_time_ms
        , source.queued_overload_time_ms
        , source.transaction_blocked_time_ms
        , source.list_external_files_time_ms
        , source.execution_time_ms
        , source.bytes_scanned
        , source.percentage_scanned_from_cache
        , source.bytes_written
        , source.bytes_written_to_result
        , source.bytes_read_from_result
        , source.rows_produced
        , source.rows_inserted
        , source.rows_updated
        , source.rows_deleted
        , source.rows_unloaded
        , source.bytes_deleted
        , source.partitions_scanned
        , source.partitions_total
        , source.bytes_spilled_to_local_storage
        , source.bytes_spilled_to_remote_storage
        , source.bytes_sent_over_the_network
        , source.outbound_data_transfer_cloud
        , source.outbound_data_transfer_region
        , source.outbound_data_transfer_bytes
        , source.inbound_data_transfer_cloud
        , source.inbound_data_transfer_region
        , source.inbound_data_transfer_bytes
        , source.release_version
        , source.external_function_total_invocations
        , source.external_function_total_sent_rows
        , source.external_function_total_received_rows
        , source.external_function_total_sent_bytes
        , source.external_function_total_received_bytes
        , source.query_load_percent
        , source.is_client_generated_statement
        , source.query_acceleration_bytes_scanned
        , source.query_acceleration_partitions_scanned
        , source.query_acceleration_upper_limit_scale_factor
        , source.parent_query_id
        , source.root_query_id
        , source.cortex_credits_by_function
        , source.cortex_usage_details
    );
END;

-- ------------------------------------------------------------
-- 5. Nightly task
-- ------------------------------------------------------------
CREATE OR REPLACE TASK task_query_history_enriched_refresh
    WAREHOUSE = identifier($task_warehouse)
    SCHEDULE  = $task_refresh_cron
AS CALL sp_query_history_enriched_refresh(3);

ALTER TASK task_query_history_enriched_refresh RESUME;

-- ------------------------------------------------------------
-- 6. Initial load (backfills the last 365 days)
--    ACCOUNT_USAGE.QUERY_HISTORY retains up to 1 year; adjust as needed.
-- ------------------------------------------------------------
CALL sp_query_history_enriched_refresh(180);
