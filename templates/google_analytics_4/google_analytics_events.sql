/*************************************************************************************
*  
*   Name: query_history_enriched.sql
*   Dev:  Oscar Bashaw (setup and incremental materialization), Select.dev (wrote the query_history_enriched calculation)
*   Date: Nov 29 2023
*   Summary: create query_history_enriched table and set up incremental materialization (inserts)
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
*************************************************************************************/


-- things to get from user:

-- current database of raw ga4 data
set ga_raw_data_dest_db = 'name of database with raw GA4 data from Snowflake connector';
-- current schema of raw ga4 data
set ga_raw_data_dest_schema = 'name of schema with raw GA4 data from Snowflake connector';
-- current table of raw ga4 data
set ga_raw_data_dest_table = 'name of existing table with raw GA4 data from Snowflake connector';


-- target database of flattened ga4 data
set ga_modeled_data_target_db = 'name of database where modeled GA4 data will live; needs to exist before running script';
-- target schema of flattened ga4 data
set ga_modeled_data_target_schema = 'name of schema where modeled GA4 data will live; does not need to exist before running script';

-- materialization role name (also the role that will own the finished table)
set materialization_role_name = 'role that has access to the raw data and can own the modeled data';
-- materialization warehouse to use
set materialization_warehouse_name = 'name of materialization warehouse';
-- materialization cron string
set materialization_CRON_string = 'USING CRON 0 3 * * Mon-Fri America/Los_Angeles';

-- sigma role name
set sigma_role_name = 'name of role used in Sigma connection';


--setup:
-- set session context

use role sysadmin;
-- grant things as needed
grant usage on database identifier($ga_raw_data_dest_db) to role identifier($materialization_role_name);
grant usage on schema identifier($ga_raw_data_dest_db).identifier($ga_raw_data_dest_schema) to role identifier($materialization_role_name);
grant select on table identifier($ga_raw_data_dest_db).identifier($ga_raw_data_dest_schema).identifier($ga_raw_data_dest_table) to role identifier($materialization_role_name);

grant usage on warehouse identifier($materialization_warehouse_name) to role identifier($materialization_warehouse_name);
grant create schema on database identifier($ga_modeled_data_target_db) to role identifier($materialization_role_name);
grant execute task on account to role identifier($materialization_role_name);

-- create things as needed
use role identifier($materialization_role_name);
use warehouse identifier($materialization_warehouse_name)
create schema if not exists identifier($ga_modeled_data_target_db).identifier($ga_modeled_data_target_schema);

--seed:
-- create table flattened events

create or replace table identifier($ga_modeled_data_target_db).identifier($ga_modeled_data_target_schema).events as (
with raw_data as (
  select * 
  from identifier($ga_raw_data_dest_db).identifier($ga_raw_data_dest_schema).identifier($ga_raw_data_dest_table)
  where to_timestamp(raw:"event_timestamp"::int, 6) <= date_trunc(day, current_date())
)

, parsed_data as (
  select
    to_date(raw:"event_date"::string, 'yyyymmdd') as event_date
    , to_timestamp(raw:"event_timestamp"::int, 6) as event_timestamp
    , raw:"event_name"::string as event_name
    , parse_json(raw:"event_params") as event_params
    , to_timestamp(raw:"event_previous_timestamp"::int, 6) as event_previous_timestamp
    , raw:"event_value_in_usd"::float as event_value_in_usd
    , raw:"event_bundle_sequence_id"::int as event_bundle_sequence_id
    , raw:"event_dimensions"::string as event_dimensions
    , raw:"event_server_timestamp_offset"::int as event_server_timestamp_offset
    , raw:"user_id"::string as user_id
    , raw:"user_pseudo_id"::string as user_pseudo_id
    , raw:"privacy_info"."analytics_storage"::string as privacy_info_analytics_storage
    , raw:"privacy_info"."ads_storage"::string as privacy_info_ads_storage
    , raw:"privacy_info"."uses_transient_token"::string as privacy_info_uses_transient_token
    , raw:"user_properties" as user_properties
    , to_timestamp(raw:"user_first_touch_timestamp"::int, 6) as user_first_touch_timestamp
    , raw:"user_ltv"."revenue"::float as user_ltv_revenue
    , raw:"user_ltv"."currency"::string as user_ltv_currency
    , raw:"device"."category"::string as device_category
    , raw:"device"."mobile_brand_name"::string as device_mobile_brand_name
    , raw:"device"."mobile_model_name"::string as device_mobile_model_name
    , raw:"device"."mobile_marketing_name"::string as device_mobile_marketing_name
    , raw:"device"."mobile_os_hardware_model"::string as device_mobile_os_hardware_model
    , raw:"device"."operating_system"::string as device_operating_system
    , raw:"device"."operating_system_version"::string as device_operating_system_version
    , raw:"device"."vendor_id"::string as device_vendor_id
    , raw:"device"."advertising_id"::string as device_advertising_id
    , raw:"device"."language"::string as device_language
    , raw:"device"."is_limited_ad_tracking"::boolean as device_is_limited_ad_tracking
    , raw:"device"."time_zone_offset_seconds"::int as device_time_zone_offset_seconds
    , raw:"device"."browser"::string as device_browser
    , raw:"device"."browser_version"::string as device_browser_version
    , raw:"device"."web_info"."browser"::string as device_web_info_browser
    , raw:"device"."web_info"."browser_version"::string as device_web_info_browser_version
    , raw:"device"."web_info"."hostname"::string as device_web_info_hostname
    , raw:"geo"."continent"::string as geo_continent
    , raw:"geo"."country"::string as geo_country
    , raw:"geo"."region"::string as geo_region
    , raw:"geo"."city"::string as geo_city
    , raw:"geo"."sub_continent"::string as geo_sub_continent
    , raw:"geo"."metro"::string as geo_metro
    , raw:"app_info"."id"::string as app_info_id
    , raw:"app_info"."version"::string as app_info_version
    , raw:"app_info"."install_store"::string as app_info_install_store
    , raw:"app_info"."firebase_app_id"::string as app_info_firebase_app_id
    , raw:"app_info"."install_source"::string as app_info_install_source
    , raw:"traffic_source"."name"::string as traffic_source_name
    , raw:"traffic_source"."medium"::string as traffic_medium
    , raw:"traffic_source"."source"::string as traffic_source
    , raw:"stream_id"::string as stream_id
    , raw:"platform"::string as platform
    , raw:"event_dimensions"."hostname"::string as event_dimensions_hostname
    , raw:"ecommerce"."total_item_quantity"::int as ecommerce_total_item_quantity
    , raw:"ecommerce"."purchase_revenue_in_usd"::float as ecommerce_purchase_revenue_in_usd
    , raw:"ecommerce"."purchase_revenue"::float as ecommerce_purchase_revenue
    , raw:"ecommerce"."refund_value_in_usd"::float as ecommerce_refund_value_in_usd
    , raw:"ecommerce"."refund_value"::float as ecommerce_refund_value
    , raw:"ecommerce"."shipping_value_in_usd"::float as ecommerce_shipping_value_in_usd
    , raw:"ecommerce"."shipping_value"::float as ecommerce_shipping_value
    , raw:"ecommerce"."tax_value_in_usd"::float as ecommerce_tax_value_in_usd
    , raw:"ecommerce"."tax_value"::float as ecommerce_tax_value
    , raw:"ecommerce"."unique_items"::int as ecommerce_unique_items
    , raw:"ecommerce"."transaction_id"::string as ecommerce_transaction_id
    , raw:"items" as items
    , raw:"collected_traffic_source"."manual_campaign_id"::string as collected_trafic_source_manual_campaign_id
    , raw:"collected_traffic_source"."manual_campaign_name"::string as collected_trafic_source_manual_campaign_name
    , raw:"collected_traffic_source"."manual_source"::string as collected_trafic_source_manual_source
    , raw:"collected_traffic_source"."manual_medium"::string as collected_trafic_source_manual_medium
    , raw:"collected_traffic_source"."manual_term"::string as collected_trafic_source_manual_term
    , raw:"collected_traffic_source"."manual_content"::string as collected_trafic_source_manual_content
    , raw:"collected_traffic_source"."gclid"::string as collected_trafic_source_gclid
    , raw:"collected_traffic_source"."dclid"::string as collected_trafic_source_dclid
    , raw:"collected_traffic_source"."srsltid"::string as collected_trafic_source_srsltid
  from raw_data 
)

, final as (
  select
    event_date
    , event_timestamp
    , user_pseudo_id
    , traffic_medium
    , traffic_source
    , traffic_source_name
    , event_name
    , geo_country
    , geo_city
    , device_web_info_hostname as host_name
    , platform
    , max(case when params.value:key::string = 'ga_session_id' then params.value:value:int_value end)::int as ga_session_id
    , max(case when params.value:key::string = 'engaged_session_event' then params.value:value:int_value end)::int as engaged_session_event
    , max(case when params.value:key::string = 'ga_session_number' then params.value:value:int_value end)::int as ga_session_number
    , max(case when params.value:key::string = 'page_title' then params.value:value:string_value end)::string as page_title
    , max(case when params.value:key::string = 'page_location' then params.value:value:string_value end)::string as page_location
    , parse_url(page_location, 1) as page_url_parsed
    , page_url_parsed:parameters.utm_term::string as utm_term
    , page_url_parsed:parameters.utm_medium::string as utm_medium
    , page_url_parsed:parameters.utm_campaign::string as utm_campaign
    , case 
        when page_url_parsed:path::string = '' then 'home' 
        else split_part(page_url_parsed:path::string, '/', 1)
      end as website_bucket
    , max(case when params.value:key::string = 'page_referrer' then params.value:value:string_value end)::string as page_referrer
    , max(case when params.value:key::string = 'session_engaged' then params.value:value:string_value end)::int as session_engaged
    , max(case when params.value:key::string = 'campaign' then params.value:value:string_value end)::string as campaign_name
    , div0(max(case when params.value:key::string = 'engagement_time_msec' then params.value:value:int_value end)::int, 1000) as engagement_time_sec
  from parsed_data
  , lateral flatten(input => parsed_data.event_params) params
  group by all
  order by event_timestamp asc
)

select
  event_date
  , event_timestamp
  , user_pseudo_id
  , traffic_medium
  , traffic_source
  , traffic_source_name
  , event_name
  , utm_term
  , utm_medium
  , utm_campaign
  , geo_country
  , geo_city
  , host_name
  , platform
  , ga_session_id
  , engaged_session_event
  , ga_session_number
  , page_title
  , page_location
  , page_url_parsed
  , website_bucket
  , page_referrer
  , session_engaged
  , campaign_name
  , engagement_time_sec
  , md5(concat(
      event_timestamp
      , user_pseudo_id
      , event_name
      , website_bucket
      , page_location
    )) as ga_event_id
from final
)
;


-- grant sigma role access to table
grant usage on database identifier($ga_modeled_data_target_db) to role identifier($sigma_role_name);
grant usage on schema identifier($ga_modeled_data_target_db).identifier($ga_modeled_data_target_schema) to role identifier($sigma_role_name);
grant select on table identifier($ga_modeled_data_target_db).identifier($ga_modeled_data_target_schema).events to role identifier($sigma_role_name);

--setup materialization:
-- where to_timestamp(raw:"event_timestamp"::int, 6)
create or replace procedure identifier($ga_modeled_data_target_db).identifier($ga_modeled_data_target_schema).usp_materialize_ga_events()
returns string
language javascript
as 
$$
try {
    snowflake.execute({sqlText: 'begin transaction;'});
    let materialization_query = `
    insert into events 
    with last_inserted_event as (
        select max(event_timestamp) as last_inserted_event_ts
        from events
    ) 
    , raw_data as (
        select * 
        from identifier($ga_raw_data_dest_db).identifier($ga_raw_data_dest_schema).identifier($ga_raw_data_dest_table)
        where to_timestamp(raw:"event_timestamp"::int, 6) > (select last_inserted_event_ts from last_inserted_event)
        )

    , parsed_data as (
        select
            to_date(raw:"event_date"::string, 'yyyymmdd') as event_date
            , to_timestamp(raw:"event_timestamp"::int, 6) as event_timestamp
            , raw:"event_name"::string as event_name
            , parse_json(raw:"event_params") as event_params
            , to_timestamp(raw:"event_previous_timestamp"::int, 6) as event_previous_timestamp
            , raw:"event_value_in_usd"::float as event_value_in_usd
            , raw:"event_bundle_sequence_id"::int as event_bundle_sequence_id
            , raw:"event_dimensions"::string as event_dimensions
            , raw:"event_server_timestamp_offset"::int as event_server_timestamp_offset
            , raw:"user_id"::string as user_id
            , raw:"user_pseudo_id"::string as user_pseudo_id
            , raw:"privacy_info"."analytics_storage"::string as privacy_info_analytics_storage
            , raw:"privacy_info"."ads_storage"::string as privacy_info_ads_storage
            , raw:"privacy_info"."uses_transient_token"::string as privacy_info_uses_transient_token
            , raw:"user_properties" as user_properties
            , to_timestamp(raw:"user_first_touch_timestamp"::int, 6) as user_first_touch_timestamp
            , raw:"user_ltv"."revenue"::float as user_ltv_revenue
            , raw:"user_ltv"."currency"::string as user_ltv_currency
            , raw:"device"."category"::string as device_category
            , raw:"device"."mobile_brand_name"::string as device_mobile_brand_name
            , raw:"device"."mobile_model_name"::string as device_mobile_model_name
            , raw:"device"."mobile_marketing_name"::string as device_mobile_marketing_name
            , raw:"device"."mobile_os_hardware_model"::string as device_mobile_os_hardware_model
            , raw:"device"."operating_system"::string as device_operating_system
            , raw:"device"."operating_system_version"::string as device_operating_system_version
            , raw:"device"."vendor_id"::string as device_vendor_id
            , raw:"device"."advertising_id"::string as device_advertising_id
            , raw:"device"."language"::string as device_language
            , raw:"device"."is_limited_ad_tracking"::boolean as device_is_limited_ad_tracking
            , raw:"device"."time_zone_offset_seconds"::int as device_time_zone_offset_seconds
            , raw:"device"."browser"::string as device_browser
            , raw:"device"."browser_version"::string as device_browser_version
            , raw:"device"."web_info"."browser"::string as device_web_info_browser
            , raw:"device"."web_info"."browser_version"::string as device_web_info_browser_version
            , raw:"device"."web_info"."hostname"::string as device_web_info_hostname
            , raw:"geo"."continent"::string as geo_continent
            , raw:"geo"."country"::string as geo_country
            , raw:"geo"."region"::string as geo_region
            , raw:"geo"."city"::string as geo_city
            , raw:"geo"."sub_continent"::string as geo_sub_continent
            , raw:"geo"."metro"::string as geo_metro
            , raw:"app_info"."id"::string as app_info_id
            , raw:"app_info"."version"::string as app_info_version
            , raw:"app_info"."install_store"::string as app_info_install_store
            , raw:"app_info"."firebase_app_id"::string as app_info_firebase_app_id
            , raw:"app_info"."install_source"::string as app_info_install_source
            , raw:"traffic_source"."name"::string as traffic_source_name
            , raw:"traffic_source"."medium"::string as traffic_medium
            , raw:"traffic_source"."source"::string as traffic_source
            , raw:"stream_id"::string as stream_id
            , raw:"platform"::string as platform
            , raw:"event_dimensions"."hostname"::string as event_dimensions_hostname
            , raw:"ecommerce"."total_item_quantity"::int as ecommerce_total_item_quantity
            , raw:"ecommerce"."purchase_revenue_in_usd"::float as ecommerce_purchase_revenue_in_usd
            , raw:"ecommerce"."purchase_revenue"::float as ecommerce_purchase_revenue
            , raw:"ecommerce"."refund_value_in_usd"::float as ecommerce_refund_value_in_usd
            , raw:"ecommerce"."refund_value"::float as ecommerce_refund_value
            , raw:"ecommerce"."shipping_value_in_usd"::float as ecommerce_shipping_value_in_usd
            , raw:"ecommerce"."shipping_value"::float as ecommerce_shipping_value
            , raw:"ecommerce"."tax_value_in_usd"::float as ecommerce_tax_value_in_usd
            , raw:"ecommerce"."tax_value"::float as ecommerce_tax_value
            , raw:"ecommerce"."unique_items"::int as ecommerce_unique_items
            , raw:"ecommerce"."transaction_id"::string as ecommerce_transaction_id
            , raw:"items" as items
            , raw:"collected_traffic_source"."manual_campaign_id"::string as collected_trafic_source_manual_campaign_id
            , raw:"collected_traffic_source"."manual_campaign_name"::string as collected_trafic_source_manual_campaign_name
            , raw:"collected_traffic_source"."manual_source"::string as collected_trafic_source_manual_source
            , raw:"collected_traffic_source"."manual_medium"::string as collected_trafic_source_manual_medium
            , raw:"collected_traffic_source"."manual_term"::string as collected_trafic_source_manual_term
            , raw:"collected_traffic_source"."manual_content"::string as collected_trafic_source_manual_content
            , raw:"collected_traffic_source"."gclid"::string as collected_trafic_source_gclid
            , raw:"collected_traffic_source"."dclid"::string as collected_trafic_source_dclid
            , raw:"collected_traffic_source"."srsltid"::string as collected_trafic_source_srsltid
        from raw_data 
        )

    , final as (
        select
            event_date
            , event_timestamp
            , user_pseudo_id
            , traffic_medium
            , traffic_source
            , traffic_source_name
            , event_name
            , geo_country
            , geo_city
            , device_web_info_hostname as host_name
            , platform
            , max(case when params.value:key::string = 'ga_session_id' then params.value:value:int_value end)::int as ga_session_id
            , max(case when params.value:key::string = 'engaged_session_event' then params.value:value:int_value end)::int as engaged_session_event
            , max(case when params.value:key::string = 'ga_session_number' then params.value:value:int_value end)::int as ga_session_number
            , max(case when params.value:key::string = 'page_title' then params.value:value:string_value end)::string as page_title
            , max(case when params.value:key::string = 'page_location' then params.value:value:string_value end)::string as page_location
            , parse_url(page_location, 1) as page_url_parsed
            , page_url_parsed:parameters.utm_term::string as utm_term
            , page_url_parsed:parameters.utm_medium::string as utm_medium
            , page_url_parsed:parameters.utm_campaign::string as utm_campaign
            , case 
                when page_url_parsed:path::string = '' then 'home' 
                else split_part(page_url_parsed:path::string, '/', 1)
            end as website_bucket
            , max(case when params.value:key::string = 'page_referrer' then params.value:value:string_value end)::string as page_referrer
            , max(case when params.value:key::string = 'session_engaged' then params.value:value:string_value end)::int as session_engaged
            , max(case when params.value:key::string = 'campaign' then params.value:value:string_value end)::string as campaign_name
            , div0(max(case when params.value:key::string = 'engagement_time_msec' then params.value:value:int_value end)::int, 1000) as engagement_time_sec
        from parsed_data
        , lateral flatten(input => parsed_data.event_params) params
        group by all
        order by event_timestamp asc
        )

    select
    event_date
    , event_timestamp
    , user_pseudo_id
    , traffic_medium
    , traffic_source
    , traffic_source_name
    , event_name
    , utm_term
    , utm_medium
    , utm_campaign
    , geo_country
    , geo_city
    , host_name
    , platform
    , ga_session_id
    , engaged_session_event
    , ga_session_number
    , page_title
    , page_location
    , page_url_parsed
    , website_bucket
    , page_referrer
    , session_engaged
    , campaign_name
    , engagement_time_sec
    , md5(concat(
        event_timestamp
        , user_pseudo_id
        , event_name
        , website_bucket
        , page_location
        )) as ga_event_id
    from final
    ;`;
    snowflake.execute({sqlText: materialization_query});
    snowflake.execute({sqlText: 'commit;'});
    return "events table successfully materialized";
} catch (err) {
    snowflake.execute({sqlText: 'rollback;'});
    return `Error: ${err}`;
}
$$;
-- create task
create or replace task task_call_usp_materialize_ga_events
warehouse = $materialization_warehouse_name
schedule = $materialization_CRON_string
as
call usp_materialize_ga_events();


-- resume task

alter task task_call_usp_materialize_ga_events resume;


