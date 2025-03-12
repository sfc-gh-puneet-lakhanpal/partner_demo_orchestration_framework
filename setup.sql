use role sysadmin;
use warehouse large_wh;
create database if not exists agentic_db;
use database agentic_db;
create schema if not exists orchestration_framework_sch;
use schema orchestration_framework_sch;
CREATE STAGE if not exists orchestration_framework_stage 
	URL = 's3://sfquickstarts/misc/orchestration_framework/' 
	DIRECTORY = ( ENABLE = true );

ls @orchestration_framework_stage;

CREATE FILE FORMAT if not exists data_parquet_format TYPE = parquet;

-- DATA FOR CORTEX ANALYST
-- data table 1: analyst tickets
CREATE or replace TABLE ANALYST_TICKETS
  USING TEMPLATE (
    SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
      FROM TABLE(
        INFER_SCHEMA(
          LOCATION=>'@orchestration_framework_stage/analyst_tickets/',
          FILE_FORMAT=>'data_parquet_format'
        )
      ));

COPY INTO ANALYST_TICKETS FROM @orchestration_framework_stage/analyst_tickets/ FILE_FORMAT = (FORMAT_NAME= 'data_parquet_format') MATCH_BY_COLUMN_NAME=CASE_INSENSITIVE;

select * from ANALYST_TICKETS limit 10;

-- data table 2: analyst rides
CREATE OR REPLACE TABLE ANALYST_RIDES
  USING TEMPLATE (
    SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
      FROM TABLE(
        INFER_SCHEMA(
          LOCATION=>'@orchestration_framework_stage/analyst_rides/',
          FILE_FORMAT=>'data_parquet_format'
        )
      ));

COPY INTO ANALYST_RIDES FROM @orchestration_framework_stage/analyst_rides/ FILE_FORMAT = (FORMAT_NAME= 'data_parquet_format') MATCH_BY_COLUMN_NAME=CASE_INSENSITIVE;

select * from analyst_rides limit 10;

-- DATA FOR CORTEX SEARCH

-- data table 3: search domains

CREATE OR REPLACE TABLE SEARCH_DOMAINS
  USING TEMPLATE (
    SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
      FROM TABLE(
        INFER_SCHEMA(
          LOCATION=>'@orchestration_framework_stage/search_domains/',
          FILE_FORMAT=>'data_parquet_format'
        )
      ));

COPY INTO SEARCH_DOMAINS FROM @orchestration_framework_stage/search_domains/ FILE_FORMAT = (FORMAT_NAME= 'data_parquet_format') MATCH_BY_COLUMN_NAME=CASE_INSENSITIVE;

select * from SEARCH_DOMAINS limit 10;

-- data table 4: search tickets

CREATE OR REPLACE TABLE search_tickets
  USING TEMPLATE (
    SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
      FROM TABLE(
        INFER_SCHEMA(
          LOCATION=>'@orchestration_framework_stage/search_tickets/',
          FILE_FORMAT=>'data_parquet_format'
        )
      ));

COPY INTO search_tickets FROM @orchestration_framework_stage/search_tickets/ FILE_FORMAT = (FORMAT_NAME= 'data_parquet_format') MATCH_BY_COLUMN_NAME=CASE_INSENSITIVE;

select * from search_tickets limit 10;
select distinct feature from search_tickets;

-- data table 5: search topics
CREATE OR REPLACE TABLE SEARCH_TOPICS
  USING TEMPLATE (
    SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
      FROM TABLE(
        INFER_SCHEMA(
          LOCATION=>'@orchestration_framework_stage/search_topics/',
          FILE_FORMAT=>'data_parquet_format'
        )
      ));

COPY INTO SEARCH_TOPICS FROM @orchestration_framework_stage/search_topics/ FILE_FORMAT = (FORMAT_NAME= 'data_parquet_format') MATCH_BY_COLUMN_NAME=CASE_INSENSITIVE;

select * from SEARCH_TOPICS limit 10;

show tables in schema;

select count(*) from ANALYST_RIDES; --33916974
select count(*) from ANALYST_TICKETS; --177892
select count(*) from SEARCH_DOMAINS; --48
select count(*) from SEARCH_TICKETS; --177892
select count(*) from SEARCH_TOPICS; --1920

--- create cortex search  services

CREATE OR REPLACE CORTEX SEARCH SERVICE topic_search
  ON TOPIC_SUMMARY
  ATTRIBUTES domain,topic,quarter,case_count
  WAREHOUSE = LARGE_WH
  TARGET_LAG = '1 hour'
AS (
  SELECT
      TOPIC_SUMMARY,
      TOPIC,
      DOMAIN,
      QUARTER,
      CASE_COUNT
  FROM SEARCH_TOPICS
);


-- domain search service
CREATE OR REPLACE CORTEX SEARCH SERVICE domain_search
  ON DOMAIN_SUMMARY
  ATTRIBUTES domain,quarter
  WAREHOUSE = LARGE_WH
  TARGET_LAG = '1 hour'
AS (
  SELECT
      DOMAIN_SUMMARY,
      DOMAIN,
      QUARTER,
  FROM SEARCH_DOMAINS
);


-- cases search service 
CREATE OR REPLACE CORTEX SEARCH SERVICE case_search
  ON TICKET_BODY
  ATTRIBUTES domain,feature,topic,quarter,ticket_id,severity
  WAREHOUSE = LARGE_WH
  TARGET_LAG = '1 hour'
AS (
  SELECT
      TICKET_BODY::text as TICKET_BODY,
      FEATURE,
      TOPIC_HEALTH_SCORE,
      SEVERITY,
      YEAR,
      TICKET_ID,
      TOPIC,
      DOMAIN,
      QUARTER,
  FROM SEARCH_TICKETS
);

CREATE STAGE IF NOT EXISTS SEMANTIC_YAMLS 
	DIRECTORY = ( ENABLE = true ) 
	ENCRYPTION = ( TYPE = 'SNOWFLAKE_SSE' );
    
-- copy semantic models
copy files into @semantic_yamls
from @orchestration_framework_stage/semantic_models/;