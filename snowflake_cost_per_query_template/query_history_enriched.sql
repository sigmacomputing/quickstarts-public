/*************************************************************************************
*  
*   Name: query_history_enriched.sql
*   Dev:  Oscar Bashaw
*   Date: Oct 7 2024
*   Summary: create query_history_enriched table and set up incremental materialization
*   Desc: This series of commands will do the following:
*           1. Set session variables
*           2. Create the query_history_enriched table that includes all queries started on or before yesterday
*           3. Grant the role used in your Sigma connection access to the query_history_enriched table
*           4. Create a stored procedure that enriches queries not yet in the query_history_enriched table (and 
*              that were run on or before the most recently completed day) and insert them into query_history_enriched
*           5. Create and start a task to call that stored procedure using the specified CRON string (Once per day Mon-Fri at 3am PT)
*          
*           
*   Prereqs: To run this script the following is required:
*           - Ability to use the SYSADMIN role (just briefly, to give the proper privileges to another role)
*           - The name of the role used in your Sigma connection
*           - Verify that there is data in the views in the SNOWFLAKE.ORGANIZATION_USAGE schema
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
    with daily_rates as (
        select date
        , max(iff(service_type = 'WAREHOUSE_METERING', effective_rate, null)) as warehouse_metering_rate
        , max(iff(service_type = 'QUERY_ACCELERATION', effective_rate, null)) as query_acceleration_rate 
        , max(iff(service_type = 'CLOUD_SERVICES', effective_rate, null)) as cloud_services_rate 
        from snowflake.organization_usage.rate_sheet_daily 
        where account_locator = current_account() 
        and service_type in ('WAREHOUSE_METERING', 'QUERY_ACCELERATION', 'CLOUD_SERVICES')
        group by date
    )

    , query_attribution_history as (
        select query_id
        , credits_attributed_compute
        , credits_used_query_acceleration
        , parent_query_id
        , root_query_id
        from snowflake.account_usage.query_attribution_history
        where start_time < dateadd(day, -1, getdate())
    )

    , query_history as (
        select *
        from snowflake.account_usage.query_history
        where query_history.start_time < dateadd(day, -1, getdate())
    )

    , final as (
        select query_history.query_id
        , query_attribution_history.credits_attributed_compute
        , query_attribution_history.credits_attributed_compute * daily_rates.warehouse_metering_rate as compute_cost
        , query_attribution_history.credits_used_query_acceleration
        , query_attribution_history.credits_used_query_acceleration * daily_rates.query_acceleration_rate as query_acceleration_cost
        , query_history.credits_used_cloud_services
        , query_history.credits_used_cloud_services * daily_rates.cloud_services_rate as cloud_services_cost
        , (coalesce(compute_cost, 0) + coalesce(query_acceleration_cost, 0) + coalesce(cloud_services_cost, 0)) as total_cost
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
        from query_attribution_history
        left join query_history on query_history.query_id = query_attribution_history.query_id
        left join daily_rates on to_date(query_history.start_time) = daily_rates.date
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
            
            , daily_rates as (
                select date
                , max(iff(service_type = 'WAREHOUSE_METERING', effective_rate, null)) as warehouse_metering_rate
                , max(iff(service_type = 'QUERY_ACCELERATION', effective_rate, null)) as query_acceleration_rate 
                , max(iff(service_type = 'CLOUD_SERVICES', effective_rate, null)) as cloud_services_rate 
                from snowflake.organization_usage.rate_sheet_daily 
                where account_locator = current_account() 
                and service_type in ('WAREHOUSE_METERING', 'QUERY_ACCELERATION', 'CLOUD_SERVICES')
                group by date
            )

            , query_attribution_history as (
                select query_attribution_history.query_id
                , query_attribution_history.credits_attributed_compute
                , query_attribution_history.credits_used_query_acceleration
                , query_attribution_history.parent_query_id
                , query_attribution_history.root_query_id
                from snowflake.account_usage.query_attribution_history query_attribution_history
                , last_enriched_query
                where query_attribution_history.start_time > last_enriched_query.last_enriched_query_start_time
                and query_attribution_history.start_time < dateadd(hour, -12, getdate())
            )

            , query_history as (
                select query_history.*
                from snowflake.account_usage.query_history query_history
                , last_enriched_query
                where query_history.start_time > last_enriched_query.last_enriched_query_start_time
                and query_history.start_time < dateadd(hour, -3, getdate())
            )

            , final as (
                select query_history.query_id
                , query_attribution_history.credits_attributed_compute
                , query_attribution_history.credits_attributed_compute * daily_rates.warehouse_metering_rate as compute_cost
                , query_attribution_history.credits_used_query_acceleration
                , query_attribution_history.credits_used_query_acceleration * daily_rates.query_acceleration_rate as query_acceleration_cost
                , query_history.credits_used_cloud_services
                , query_history.credits_used_cloud_services * daily_rates.cloud_services_rate as cloud_services_cost
                , (coalesce(compute_cost, 0) + coalesce(query_acceleration_cost, 0) + coalesce(cloud_services_cost, 0)) as total_cost
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
                from query_attribution_history
                left join query_history on query_history.query_id = query_attribution_history.query_id
                left join daily_rates on to_date(query_history.start_time) = daily_rates.date
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