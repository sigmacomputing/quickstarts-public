-- AWS Cost and Usage Report 2.0 Snowflake Setup (for Sigma template)
-- Author: Oscar Bashaw
-- Date: Nov 2024

-----------------------
-- Create schema
-----------------------

-- specify database and schema
set cur_database = 'database that will hold aws cost report data';
set cur_schema = 'aws_billing';
set sigma_role_name = 'name of role used in Sigma connection that you will use to access final table';
set dynamic_table_warehouse = 'name of warehouse to be used for dynamic table';

-- create db and schema if they don't exist
create database if not exists identifier($cur_database);
use database identifier($cur_database);

create schema if not exists identifier($cur_schema);
use schema identifier($cur_schema);

-- file format for unloading data
create or replace file format aws_cur_2_file_format 
type = CSV
compression = gzip
field_optionally_enclosed_by = '"'
skip_header = 1
;


-- external stage for s3 bucket
create stage aws_cur_2_stage
    storage_integration = -- if using Snowflake storage integration
    credentials = (AWS_KEY_ID='' AWS_SECRET_KEY='') -- if using AWS IAM User
    encryption = (TYPE='AWS_SSE_KMS' KMS_KEY_ID = 'aws/key') -- if using AWS IAM User
    url = 's3://{s3 bucket name}/aws-cur-2-daily' -- aws-cur-2-daily is the prefix we specified in step 1
    file_format = aws_cur_2_file_format
;

-- raw cur 2.0 table
create or replace table aws_billing_daily_raw (
    bill_bill_type varchar()
    , bill_billing_entity varchar()
    , bill_billing_period_end_date timestamp_ntz
    , bill_billing_period_start_date timestamp_ntz
    , bill_invoice_id varchar()
    , bill_invoicing_entity varchar()
    , bill_payer_account_id varchar()
    , bill_payer_account_name varchar()
    , cost_category varchar()
    , discount varchar()
    , discount_bundled_discount varchar()
    , discount_total_discount varchar()
    , identity_line_item_id varchar()
    , identity_time_interval varchar()
    , line_item_availability_zone varchar()
    , line_item_blended_cost varchar()
    , line_item_blended_rate varchar()
    , line_item_currency_code varchar()
    , line_item_legal_entity varchar()
    , line_item_line_item_description varchar()
    , line_item_line_item_type varchar()
    , line_item_net_unblended_cost varchar()
    , line_item_net_unblended_rate varchar()
    , line_item_normalization_factor varchar()
    , line_item_normalized_usage_amount varchar()
    , line_item_operation varchar()
    , line_item_product_code varchar()
    , line_item_resource_id varchar()
    , line_item_tax_type varchar()
    , line_item_unblended_cost varchar()
    , line_item_unblended_rate varchar()
    , line_item_usage_account_id varchar()
    , line_item_usage_account_name varchar()
    , line_item_usage_amount varchar()
    , line_item_usage_end_date timestamp_ntz
    , line_item_usage_start_date timestamp_ntz
    , line_item_usage_type varchar()
    , pricing_currency varchar()
    , pricing_lease_contract_length varchar()
    , pricing_offering_class varchar()
    , pricing_public_on_demand_cost varchar()
    , pricing_public_on_demand_rate varchar()
    , pricing_purchase_option varchar()
    , pricing_rate_code varchar()
    , pricing_rate_id varchar()
    , pricing_term varchar()
    , pricing_unit varchar()
    , product varchar()
    , product_comment varchar()
    , product_fee_code varchar()
    , product_fee_description varchar()
    , product_from_location varchar()
    , product_from_location_type varchar()
    , product_from_region_code varchar()
    , product_instance_family varchar()
    , product_instance_type varchar()
    , product_instancesku varchar()
    , product_location varchar()
    , product_location_type varchar()
    , product_operation varchar()
    , product_pricing_unit varchar()
    , product_product_family varchar()
    , product_region_code varchar()
    , product_servicecode varchar()
    , product_sku varchar()
    , product_to_location varchar()
    , product_to_location_type varchar()
    , product_to_region_code varchar()
    , product_usagetype varchar()
    , reservation_amortized_upfront_cost_for_usage varchar()
    , reservation_amortized_upfront_fee_for_billing_period varchar()
    , reservation_availability_zone varchar()
    , reservation_effective_cost varchar()
    , reservation_end_time varchar()
    , reservation_modification_status varchar()
    , reservation_net_amortized_upfront_cost_for_usage varchar()
    , reservation_net_amortized_upfront_fee_for_billing_period varchar()
    , reservation_net_effective_cost varchar()
    , reservation_net_recurring_fee_for_usage varchar()
    , reservation_net_unused_amortized_upfront_fee_for_billing_period varchar()
    , reservation_net_unused_recurring_fee varchar()
    , reservation_net_upfront_value varchar()
    , reservation_normalized_units_per_reservation varchar()
    , reservation_number_of_reservations varchar()
    , reservation_recurring_fee_for_usage varchar()
    , reservation_reservation_a_r_n varchar()
    , reservation_start_time varchar()
    , reservation_subscription_id varchar()
    , reservation_total_reserved_normalized_units varchar()
    , reservation_total_reserved_units varchar()
    , reservation_units_per_reservation varchar()
    , reservation_unused_amortized_upfront_fee_for_billing_period varchar()
    , reservation_unused_normalized_unit_quantity varchar()
    , reservation_unused_quantity varchar()
    , reservation_unused_recurring_fee varchar()
    , reservation_upfront_value varchar()
    , resource_tags varchar()
    , savings_plan_amortized_upfront_commitment_for_billing_period varchar()
    , savings_plan_end_time varchar()
    , savings_plan_instance_type_family varchar()
    , savings_plan_net_amortized_upfront_commitment_for_billing_period varchar()
    , savings_plan_net_recurring_commitment_for_billing_period varchar()
    , savings_plan_net_savings_plan_effective_cost varchar()
    , savings_plan_offering_type varchar()
    , savings_plan_payment_option varchar()
    , savings_plan_purchase_term varchar()
    , savings_plan_recurring_commitment_for_billing_period varchar()
    , savings_plan_region varchar()
    , savings_plan_savings_plan_a_r_n varchar()
    , savings_plan_savings_plan_effective_cost varchar()
    , savings_plan_savings_plan_rate varchar()
    , savings_plan_start_time varchar()
    , savings_plan_total_commitment_to_date varchar()
    , savings_plan_used_commitment varchar()
) cluster by (to_date(line_item_usage_start_date))
;


-- create pipe
create or replace pipe aws_daily_billing_pipe 
auto_ingest = true 
as 
    copy into aws_billing_daily_raw from (
        select $1 as bill_bill_type
        , $2 as bill_billing_entity
        , $3::timestamp_ntz as bill_billing_period_end_date
        , $4::timestamp_ntz as bill_billing_period_start_date
        , $5 as bill_invoice_id
        , $6 as bill_invoicing_entity
        , $7 as bill_payer_account_id
        , $8 as bill_payer_account_name
        , $9 as cost_category
        , $10 as discount
        , $11 as discount_bundled_discount
        , $12 as discount_total_discount
        , $13 as identity_line_item_id
        , $14 as identity_time_interval
        , $15 as line_item_availability_zone
        , $16 as line_item_blended_cost
        , $17 as line_item_blended_rate
        , $18 as line_item_currency_code
        , $19 as line_item_legal_entity
        , $20 as line_item_line_item_description
        , $21 as line_item_line_item_type
        , $22 as line_item_net_unblended_cost
        , $23 as line_item_net_unblended_rate
        , $24 as line_item_normalization_factor
        , $25 as line_item_normalized_usage_amount
        , $26 as line_item_operation
        , $27 as line_item_product_code
        , $28 as line_item_resource_id
        , $29 as line_item_tax_type
        , $30 as line_item_unblended_cost
        , $31 as line_item_unblended_rate
        , $32 as line_item_usage_account_id
        , $33 as line_item_usage_account_name
        , $34 as line_item_usage_amount
        , $35::timestamp_ntz as line_item_usage_end_date
        , $36::timestamp_ntz as line_item_usage_start_date
        , $37 as line_item_usage_type
        , $38 as pricing_currency
        , $39 as pricing_lease_contract_length
        , $40 as pricing_offering_class
        , $41 as pricing_public_on_demand_cost
        , $42 as pricing_public_on_demand_rate
        , $43 as pricing_purchase_option
        , $44 as pricing_rate_code
        , $45 as pricing_rate_id
        , $46 as pricing_term
        , $47 as pricing_unit
        , $48 as product
        , $49 as product_comment
        , $50 as product_fee_code
        , $51 as product_fee_description
        , $52 as product_from_location
        , $53 as product_from_location_type
        , $54 as product_from_region_code
        , $55 as product_instance_family
        , $56 as product_instance_type
        , $57 as product_instancesku
        , $58 as product_location
        , $59 as product_location_type
        , $60 as product_operation
        , $61 as product_pricing_unit
        , $62 as product_product_family
        , $63 as product_region_code
        , $64 as product_servicecode
        , $65 as product_sku
        , $66 as product_to_location
        , $67 as product_to_location_type
        , $68 as product_to_region_code
        , $69 as product_usagetype
        , $70 as reservation_amortized_upfront_cost_for_usage
        , $71 as reservation_amortized_upfront_fee_for_billing_period
        , $72 as reservation_availability_zone
        , $73 as reservation_effective_cost
        , $74 as reservation_end_time
        , $75 as reservation_modification_status
        , $76 as reservation_net_amortized_upfront_cost_for_usage
        , $77 as reservation_net_amortized_upfront_fee_for_billing_period
        , $78 as reservation_net_effective_cost
        , $79 as reservation_net_recurring_fee_for_usage
        , $80 as reservation_net_unused_amortized_upfront_fee_for_billing_period
        , $81 as reservation_net_unused_recurring_fee
        , $82 as reservation_net_upfront_value
        , $83 as reservation_normalized_units_per_reservation
        , $84 as reservation_number_of_reservations
        , $85 as reservation_recurring_fee_for_usage
        , $86 as reservation_reservation_a_r_n
        , $87 as reservation_start_time
        , $88 as reservation_subscription_id
        , $89 as reservation_total_reserved_normalized_units
        , $90 as reservation_total_reserved_units
        , $91 as reservation_units_per_reservation
        , $92 as reservation_unused_amortized_upfront_fee_for_billing_period
        , $93 as reservation_unused_normalized_unit_quantity
        , $94 as reservation_unused_quantity
        , $95 as reservation_unused_recurring_fee
        , $96 as reservation_upfront_value
        , $97 as resource_tags
        , $98 as savings_plan_amortized_upfront_commitment_for_billing_period
        , $99 as savings_plan_end_time
        , $100 as savings_plan_instance_type_family
        , $101 as savings_plan_net_amortized_upfront_commitment_for_billing_period
        , $102 as savings_plan_net_recurring_commitment_for_billing_period
        , $103 as savings_plan_net_savings_plan_effective_cost
        , $104 as savings_plan_offering_type
        , $105 as savings_plan_payment_option
        , $106 as savings_plan_purchase_term
        , $107 as savings_plan_recurring_commitment_for_billing_period
        , $108 as savings_plan_region
        , $109 as savings_plan_savings_plan_a_r_n
        , $110 as savings_plan_savings_plan_effective_cost
        , $111 as savings_plan_savings_plan_rate
        , $112 as savings_plan_start_time
        , $113 as savings_plan_total_commitment_to_date
        , $114 as savings_plan_used_commitment
        from '@aws_cur_2_stage/aws-cur-2-daily/AWS-CUR-2-Daily-Report/data/' -- check path; verify that it takes name of AWS report name
        (file_format => 'aws_cur_2_file_format', pattern=>'.*\.csv\.gz$')
    )
;
alter pipe aws_daily_billing_pipe set pipe_execution_paused = false;
alter pipe aws_daily_billing_pipe refresh;


-- Dynamic Table for finished data
create or replace dynamic table aws_daily_usage
  target_lag = '1 hour'
  warehouse = identifier($dynamic_table_warehouse)
  refresh_mode = incremental
  initialize = on_create
  cluster by (to_date(usage_start_date), usage_account_id, product_code) -- last 2 are optional
as
    with source as (
        select * 
        from aws_billing_daily_raw
    )

    , renamed_recast as (
        select bill_bill_type as bill_type
        , bill_billing_entity as billing_entity
        , bill_billing_period_start_date as billing_period_start_date
        , bill_billing_period_end_date as billing_period_end_date
        , bill_invoice_id as invoice_id
        , bill_invoicing_entity as invoicing_entity
        , bill_payer_account_id as payer_account_id
        , bill_payer_account_name as payer_account_name
        , try_parse_json(cost_category) as cost_category
        , try_parse_json(discount) as discount
        , discount_bundled_discount::number(38, 10) as bundled_discount
        , discount_total_discount::number(38, 10) as total_discount
        , identity_line_item_id as line_item_id
        , split_part(identity_time_interval, '/', 1) as start_time
        , split_part(identity_time_interval, '/', 2) as end_time
        , line_item_availability_zone as availability_zone
        , line_item_blended_cost::number(38, 10) as blended_cost
        , line_item_blended_rate as blended_rate
        , line_item_currency_code as currency_code
        , line_item_legal_entity as legal_entity
        , line_item_line_item_description as line_item_description
        , line_item_line_item_type as line_item_type
        , line_item_net_unblended_cost::number(38, 10) as net_unblended_cost
        , line_item_net_unblended_rate as net_unblended_rate
        , line_item_normalization_factor::number(38, 10) as normalization_factor
        , line_item_normalized_usage_amount::number(38, 10) as normalized_usage_amount
        , line_item_operation as operation
        , line_item_product_code as product_code
        , line_item_resource_id as resource_id
        , line_item_tax_type as tax_type
        , line_item_unblended_cost::number(38, 10) as unblended_cost
        , line_item_unblended_rate as unblended_rate
        , line_item_usage_account_id as usage_account_id
        , line_item_usage_account_name as usage_account_name
        , line_item_usage_amount::number(38, 10) as usage_amount
        , line_item_usage_start_date as usage_start_date
        , line_item_usage_end_date as usage_end_date
        , line_item_usage_type as usage_type
        , pricing_currency as currency
        , pricing_lease_contract_length as contract_length
        , pricing_offering_class as offering_class
        , pricing_public_on_demand_cost::number(38, 10) as on_demand_cost
        , pricing_public_on_demand_rate as on_demand_rate
        , pricing_purchase_option as purchase_option
        , pricing_rate_code as rate_code
        , pricing_rate_id as rate_id
        , pricing_term as term
        , pricing_unit as usage_unit
        , try_parse_json(product) as product
        , product_comment
        , product_fee_code
        , product_fee_description
        , product_from_location as from_location
        , product_from_location_type as from_location_type
        , product_from_region_code as from_region_Code
        , product_instance_family as instance_family
        , product_instance_type as instance_type
        , product_instancesku as instance_sku
        , product_location as region -- use instead of AZ
        , product_location_type as location_type
        , product_operation as product_operation
        , product_pricing_unit as pricing_unit -- same as usage unit?
        , product_product_family as product_family
        , product_region_code as region_code -- same as region?
        , product_servicecode as service_code -- may be same as product / operation
        , product_sku as sku
        , product_to_location as to_location
        , product_to_location_type as to_location_type
        , product_to_region_code as to_region_code
        , product_usagetype as product_usage_type
        , reservation_amortized_upfront_cost_for_usage::number(38, 10) as reservation_amortized_upfront_cost_for_usage
        , reservation_amortized_upfront_fee_for_billing_period::number(38, 10) as reservation_amortized_upfront_fee_for_billing_period
        , reservation_availability_zone 
        , reservation_effective_cost::number(38, 10) as reservation_effective_cost
        , reservation_start_time
        , reservation_end_time
        , reservation_modification_status
        , reservation_net_amortized_upfront_cost_for_usage::number(38, 10) as reservation_net_amortized_upfront_cost_for_usage
        , reservation_net_amortized_upfront_fee_for_billing_period::number(38, 10) as reservation_net_amortized_upfront_fee_for_billing_period
        , reservation_net_effective_cost::number(38, 10) as reservation_net_effective_cost
        , reservation_net_recurring_fee_for_usage::number(38, 10) as reservation_net_recurring_fee_for_usage
        , reservation_net_unused_amortized_upfront_fee_for_billing_period::number(38, 10) as reservation_net_unused_amortized_upfront_fee_for_billing_period
        , reservation_net_unused_recurring_fee::number(38, 10) as reservation_net_unused_recurring_fee
        , reservation_net_upfront_value::number(38, 10) as reservation_net_upfront_value
        , reservation_normalized_units_per_reservation as normalized_units_per_reservation
        , reservation_number_of_reservations as number_of_reservations
        , reservation_recurring_fee_for_usage::number(38, 10) as amortized_recurring_fee_for_usage
        , reservation_reservation_a_r_n as reservation_arn 
        , reservation_subscription_id
        , reservation_total_reserved_normalized_units as total_reserved_normalized_units
        , reservation_total_reserved_units as total_reserved_units
        , reservation_units_per_reservation as units_per_reservation
        , reservation_unused_amortized_upfront_fee_for_billing_period::number(38, 10) as reservation_unused_amortized_upfront_fee_for_billing_period
        , reservation_unused_normalized_unit_quantity::number(38, 10) as reservation_unused_normalized_unit_quantity
        , reservation_unused_quantity::number(38, 10) as reservation_unused_ri_hours
        , reservation_unused_recurring_fee::number(38, 10) as reservation_unused_recurring_fee
        , reservation_upfront_value::number(38, 10) as reservation_upfront_price_paid
        , try_parse_json(resource_tags) as resource_tags
        , savings_plan_amortized_upfront_commitment_for_billing_period::number(38, 10) as savings_plan_amortized_upfront_commitment_for_billing_period
        , savings_plan_savings_plan_a_r_n as savings_plan_arn
        , savings_plan_start_time
        , savings_plan_end_time
        , savings_plan_instance_type_family
        , savings_plan_net_amortized_upfront_commitment_for_billing_period::number(38, 10) as savings_plan_net_amortized_upfront_commitment_for_billing_period
        , savings_plan_net_recurring_commitment_for_billing_period::number(38, 10) as savings_plan_net_recurring_commitment_for_billing_period
        , savings_plan_net_savings_plan_effective_cost::number(38, 10) as savings_plan_net_savings_plan_effective_cost
        , savings_plan_offering_type
        , savings_plan_payment_option
        , savings_plan_purchase_term
        , savings_plan_recurring_commitment_for_billing_period::number(38, 10) as savings_plan_recurring_commitment_for_billing_period
        , savings_plan_region
        , savings_plan_savings_plan_effective_cost::number(38, 10) as savings_plan_effective_cost
        , savings_plan_savings_plan_rate::number(38, 10) as savings_plan_rate
        , savings_plan_total_commitment_to_date::number(38, 10) as savings_plan_total_commitment_to_date
        , savings_plan_used_commitment::number(38, 10) as savings_plan_used_commitment
        from source
    )
    select *
    from renamed_recast
;