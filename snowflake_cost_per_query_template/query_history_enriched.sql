/*************************************************************************************
*  
*   Name: query_history_enriched.sql
*   Dev:  Oscar Bashaw (with credit to Select.dev for their cost-per-query calculation)
*   Date: Dec 13 2024
*   Summary: create query_history_enriched table and set up incremental materialization
*   Desc: This series of commands will do the following:
*           1. Set session variables
*           2. Create the query_history_enriched table that includes all queries started on or before yesterday
*           3. Grant the role used in your Sigma connection access to the query_history_enriched table
*           4. Create a stored procedure that enriches queries not yet in the query_history_enriched table (and 
*              that were run on or before the most recently completed day) and insert them into query_history_enriched
*           5. Create and start a task to call that stored procedure using the specified CRON string (Once per day Mon-Fri at 3am PT)
*                   
*   Prereqs: To run this script the following is required:
*           - Ability to use the SYSADMIN role (just briefly, to give the proper privileges to another role)
*           - The name of the role used in your Sigma connection
*           - Verify that there is data in the views in the SNOWFLAKE.ORGANIZATION_USAGE schema
*
*************************************************************************************/


---------------------------------------------------------------------------------------------------------
-- 1. Set session variables
---------------------------------------------------------------------------------------------------------
set materialization_role_name = 'name of role used while running this script';
set database_name =  'name of database where query_history_enriched will live';
set schema_name =  'name of schema where query_history_enriched will live';
set sigma_role_name = 'name of role used in Sigma connection that you will use to access this table';

-- recommend a Medium warehouse, unless your query_history table is small and daily query volumes are low.
set materialization_warehouse_name = 'name of the warehouse you want to use';

-- dont move earlier than 3 am on a given day; there is some latency for Snowflake usage data.
set task_call_usp_materialize_query_history_enriched_CRON = 'USING CRON 0 3 * * Mon-Fri America/Los_Angeles';

/*************************************************************************************
*
*   DO NOT MODIFY BELOW THIS SECTION
*
*************************************************************************************/
use database identifier($database_name);
use schema identifier($schema_name);

-- need to give the materialization role the proper permissions to create table, stored procedure and task
use role sysadmin;
grant imported privileges on database snowflake to role identifier($materialization_role_name);
grant create table on schema identifier($schema_name) to role identifier($materialization_role_name);
grant create procedure on schema identifier($schema_name) to role identifier($materialization_role_name);
grant create task on schema identifier($schema_name) to role identifier($materialization_role_name);
grant execute task on account to role identifier($materialization_role_name);

-- now use the materialization role
use role identifier($materialization_role_name);
use warehouse identifier($materialization_warehouse_name);


---------------------------------------------------------------------------------------------------------
-- 2. Create the query_history_enriched table that includes all queries ended on or before yesterday
---------------------------------------------------------------------------------------------------------
create or replace table query_history_enriched 
cluster by (to_date(start_time)) as (
    with query_history as (
        select
            *
        from snowflake.account_usage.query_history 
        where end_time < date_trunc(day, getdate())
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
        , cost_per_query.cortex_functions_credits as cortex_functions_credits
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
    order by to_date(start_time)
)
;
---------------------------------------------------------------------------------------------------------
-- 3. Grant the Sigma service role select access on this table
---------------------------------------------------------------------------------------------------------
grant usage on database identifier($database_name) to role identifier($sigma_role_name);
grant usage on schema identifier($schema_name) to role identifier($sigma_role_name);
grant select on table query_history_enriched to role identifier($sigma_role_name);


---------------------------------------------------------------------------------------------------------
-- 4. Create a stored procedure that enriches queries not yet in the query_history_enriched table
---------------------------------------------------------------------------------------------------------
create or replace procedure usp_materialize_query_history_enriched()
returns string
language javascript
as
$$
try {
    snowflake.execute({sqlText: 'begin transaction;'});
    let materialization_query = `
        insert into query_history_enriched
            with last_enriched_query as (
                select max(start_time) as last_enriched_query_start_time
                from query_history_enriched
            ) 
            
            , query_history as (
                select
                    query_history.*
                from snowflake.account_usage.query_history query_history 
                where query_history.start_time > (select last_enriched_query_start_time from last_enriched_query)
                and query_history.start_time < date_trunc(day, getdate())
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
                from snowflake.account_usage.query_history query_history
                where end_time <= (select latest_ts from stop_threshold)
                and query_history.start_time > (select last_enriched_query_start_time from last_enriched_query)
                and query_history.end_time < date_trunc(day, getdate())
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
                from snowflake.account_usage.query_attribution_history query_attribution_history
                where end_time < date_trunc(day, getdate())
                and query_attribution_history.start_time > (select last_enriched_query_start_time from last_enriched_query)
            )

            , final as (
                select 
                    query_history.query_id
                    , cost_per_query.compute_credits as credits_attributed_compute
                    , cost_per_query.compute_cost as compute_cost
                    , cost_per_query.query_acceleration_credits as credits_used_query_acceleration
                    , cost_per_query.query_acceleration_cost as query_acceleration_cost
                    , cost_per_query.cloud_services_credits as credits_used_cloud_services
                    , cost_per_query.cloud_services_cost as cloud_services_cost
                    , cost_per_query.cortex_functions_cost as cortex_functions_cost
                    , cost_per_query.cortex_functions_credits as cortex_functions_credits
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
                where query_history.start_time > (select last_enriched_query_start_time from last_enriched_query)
                    and query_history.end_time < date_trunc(day, getdate())
            )

            select *
            from final
            order by to_date(start_time)
        ;`;
    snowflake.execute({sqlText: materialization_query});
    snowflake.execute({sqlText: 'commit;'});
    return "success";
} catch (err) {
    snowflake.execute({sqlText: 'rollback;'});
    throw new Error(err);
}
$$
;


---------------------------------------------------------------------------------------------------------
-- 5. Create and start a task to call that stored procedure using the specified CRON string
---------------------------------------------------------------------------------------------------------
create or replace task task_call_usp_materialize_query_history_enriched
warehouse = $materialization_warehouse_name
schedule = $task_call_usp_materialize_query_history_enriched_CRON
as
call usp_materialize_query_history_enriched();

alter task task_call_usp_materialize_query_history_enriched resume;

---------------------------------------------------------------------------------------------------------
-- END OF FILE
---------------------------------------------------------------------------------------------------------