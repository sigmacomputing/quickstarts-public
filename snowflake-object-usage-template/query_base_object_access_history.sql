-- query_object_access
-- One row per object (table, view, UDF) accessed per query.
-- Incrementally materialized nightly via Snowflake Task + Stored Procedure using MERGE.
--
-- Configuration: replace the three variables below before running.
--   target_database  : database where the table and task will be created
--   target_schema    : schema where the table and task will be created
--   task_warehouse   : warehouse the task will use when it runs
--
-- On first run this script will:
--   1. Create the table (if it doesn't exist)
--   2. Create (or replace) the stored procedure containing the transformation logic
--   3. Wrap the stored procedure in a task for nightly execution
--   4. Resume the task
--   5. Execute the stored procedure immediately to backfill the last 180 days

SET target_database = 'target database';
SET target_schema   = 'target schema';
SET task_warehouse  = 'demo_eng_wh';

-- ------------------------------------------------------------
-- 1. Create the table
-- ------------------------------------------------------------
USE database identifier($target_database);
USE schema identifier($target_schema);

CREATE TABLE IF NOT EXISTS query_base_object_access_history (
    query_id                    VARCHAR         NOT NULL    COMMENT 'Snowflake query ID',
    object_surrogate_id         VARCHAR         NOT NULL    COMMENT 'MD5 of Snowflake object ID, object name and object domain',
    snowflake_object_id         VARCHAR                     COMMENT 'Snowflake object ID where present; unique across account and domain',
    object_name                 VARCHAR         NOT NULL    COMMENT 'Fully qualified name of the Snowflake object',
    object_domain               VARCHAR         NOT NULL    COMMENT 'The type of the base object (table, stage, view, function, etc)',
    query_start_time            TIMESTAMP_LTZ               COMMENT '',   
    query_end_time              TIMESTAMP_LTZ               COMMENT '',
    query_text                  VARCHAR                     COMMENT '',
    query_type                  VARCHAR                     COMMENT 'Snowflake query type',
    user_name                   VARCHAR                     COMMENT 'Snowflake user who executed the query',
    role_name                   VARCHAR                     COMMENT 'Snowflake role used to execute query',
    warehouse_name              VARCHAR                     COMMENT '',
    warehouse_size              VARCHAR                     COMMENT '',
    query_tag                   VARCHAR                     COMMENT 'The complete query tag sent to Snowflake',
    is_sigma_query              BOOLEAN                     COMMENT 'True if query was executed by Sigma',
    sigma_query_kind            VARCHAR                     COMMENT 'The kind of the Sigma query',
    sigma_source_url            VARCHAR                     COMMENT 'Sigma document or element where query originated',
    sigma_org_slug              VARCHAR                     COMMENT 'Sigma org where query originated',
    sigma_document_name         VARCHAR                     COMMENT 'Sigma document name where query originated',
    sigma_document_type         VARCHAR                     COMMENT 'Sigma document type where query originated',
    sigma_document_base_62_id   VARCHAR                     COMMENT 'Sigma document ID where query originated',
    sigma_request_id            VARCHAR                     COMMENT '',
    sigma_user_email            VARCHAR                     COMMENT 'Sigma user who executed the query',
    sigma_user_id               VARCHAR                     COMMENT '',
    sigma_user_email_domain     VARCHAR                     COMMENT '',
    base_object_details         VARIANT                     COMMENT 'Additional metadata about the base Snowflake object accessed'
);

-- ------------------------------------------------------------
-- 2. Stored procedure that contains the MERGE logic
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE sp_query_base_object_access_history_refresh(lookback_days FLOAT)
RETURNS STRING
LANGUAGE SQL
AS
BEGIN
    MERGE INTO query_base_object_access_history AS target
    USING (
        with objects_accessed as (
            select
                query_id
                , base_objects.value as base_object_details
                , base_objects.value:objectName::string as object_name
                , base_objects.value:objectDomain::string as object_domain
                , base_objects.value:objectId::number as snowflake_object_id
                , md5(coalesce(base_objects.value:objectId::string, 'empty-id') || '|' || object_name || '|' || object_domain) as object_surrogate_id
            from snowflake.account_usage.access_history
            , lateral flatten(input => base_objects_accessed) as base_objects
            where query_start_time >= DATEADD('day', -:lookback_days, current_timestamp())
              and object_name is not null
              and object_domain is not null
        )

        , query_details as (
            select
                query_id
                , query_text
                , query_type
                , start_time as query_start_time
                , end_time as query_end_time
                , user_name
                , role_name
                , warehouse_name
                , warehouse_size
                , query_tag
                , contains(query_tag, 'Sigma Σ') as is_sigma_query
                , try_parse_json(replace(query_tag, 'Sigma Σ ', '')) as sigma_query_tag_json
                , sigma_query_tag_json:kind::string as sigma_query_kind
                , sigma_query_tag_json:sourceUrl::string as sigma_source_url
                , parse_url(sigma_source_url, 1):path::string as sigma_source_url_path_parsed
                , split_part(sigma_source_url_path_parsed, '/', 1) as sigma_org_slug
                , split_part(sigma_source_url_path_parsed, '/', 2) as sigma_document_type
                , split_part(sigma_source_url_path_parsed, '/', 3) as sigma_document_slug
                , regexp_substr(sigma_document_slug, '[A-Za-z0-9]{22}$') as sigma_document_base_62_id
                , trim(replace(regexp_replace(sigma_document_slug, '-[A-Za-z0-9]{22}$', ''), '-', ' ')) as sigma_document_name
                , sigma_query_tag_json:"request-id"::string as sigma_request_id
                , sigma_query_tag_json:email::string as sigma_user_email
                , sigma_query_tag_json:"user-id"::string as sigma_user_id
                , split_part(split_part(sigma_user_email, '@', 2), '.', 1) as sigma_user_email_domain
            from snowflake.account_usage.query_history
            where start_time >= DATEADD('day', -:lookback_days, current_timestamp())
        )

        select
            q.query_id
            , o.object_surrogate_id
            , o.snowflake_object_id
            , o.object_name
            , o.object_domain
            , q.query_start_time
            , q.query_end_time
            , q.query_text
            , q.query_type
            , q.user_name
            , q.role_name
            , q.warehouse_name
            , q.warehouse_size
            , q.query_tag
            , q.is_sigma_query
            , q.sigma_query_kind
            , q.sigma_source_url
            , q.sigma_org_slug
            , q.sigma_document_name
            , q.sigma_document_type
            , q.sigma_document_base_62_id
            , q.sigma_request_id
            , q.sigma_user_email
            , q.sigma_user_id
            , q.sigma_user_email_domain
            , o.base_object_details
        from query_details q
        inner join objects_accessed o on o.query_id = q.query_id

    ) AS source
    ON  target.query_id = source.query_id
    AND target.object_surrogate_id = source.object_surrogate_id

    WHEN MATCHED THEN UPDATE SET
        target.snowflake_object_id         = source.snowflake_object_id
        , target.object_name               = source.object_name
        , target.object_domain             = source.object_domain
        , target.query_start_time          = source.query_start_time
        , target.query_end_time            = source.query_end_time
        , target.query_text                = source.query_text
        , target.query_type                = source.query_type
        , target.user_name                 = source.user_name
        , target.role_name                 = source.role_name
        , target.warehouse_name            = source.warehouse_name
        , target.warehouse_size            = source.warehouse_size
        , target.query_tag                 = source.query_tag
        , target.is_sigma_query            = source.is_sigma_query
        , target.sigma_query_kind          = source.sigma_query_kind
        , target.sigma_source_url          = source.sigma_source_url
        , target.sigma_org_slug            = source.sigma_org_slug
        , target.sigma_document_name       = source.sigma_document_name
        , target.sigma_document_type       = source.sigma_document_type
        , target.sigma_document_base_62_id = source.sigma_document_base_62_id
        , target.sigma_request_id          = source.sigma_request_id
        , target.sigma_user_email          = source.sigma_user_email
        , target.sigma_user_id             = source.sigma_user_id
        , target.sigma_user_email_domain   = source.sigma_user_email_domain
        , target.base_object_details       = source.base_object_details

    WHEN NOT MATCHED THEN INSERT (
        query_id
        , object_surrogate_id
        , snowflake_object_id
        , object_name
        , object_domain
        , query_start_time
        , query_end_time
        , query_text
        , query_type
        , user_name
        , role_name
        , warehouse_name
        , warehouse_size
        , query_tag
        , is_sigma_query
        , sigma_query_kind
        , sigma_source_url
        , sigma_org_slug
        , sigma_document_name
        , sigma_document_type
        , sigma_document_base_62_id
        , sigma_request_id
        , sigma_user_email
        , sigma_user_id
        , sigma_user_email_domain
        , base_object_details
    )
    VALUES (
        source.query_id
        , source.object_surrogate_id
        , source.snowflake_object_id
        , source.object_name
        , source.object_domain
        , source.query_start_time
        , source.query_end_time
        , source.query_text
        , source.query_type
        , source.user_name
        , source.role_name
        , source.warehouse_name
        , source.warehouse_size
        , source.query_tag
        , source.is_sigma_query
        , source.sigma_query_kind
        , source.sigma_org_slug
        , source.sigma_source_url
        , source.sigma_document_name
        , source.sigma_document_type
        , source.sigma_document_base_62_id
        , source.sigma_request_id
        , source.sigma_user_email
        , source.sigma_user_id
        , source.sigma_user_email_domain
        , source.base_object_details
    );
END;


-- ------------------------------------------------------------
-- 3. Nightly task
-- ------------------------------------------------------------

CREATE OR REPLACE TASK task_query_base_object_access_history_refresh
    WAREHOUSE = identifier($task_warehouse)
    SCHEDULE  = 'USING CRON 0 6 * * * UTC'   -- 6am UTC daily; adjust as needed
AS CALL sp_query_base_object_access_history_refresh(3);

-- ------------------------------------------------------------
-- 4. Resume the task
-- ------------------------------------------------------------

ALTER TASK task_query_base_object_access_history_refresh RESUME;


-- ------------------------------------------------------------
-- 5. Initial load (backfills the last 6 months)
-- ------------------------------------------------------------

CALL sp_query_base_object_access_history_refresh(180);

