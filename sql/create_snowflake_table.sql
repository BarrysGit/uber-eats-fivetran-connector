-- Create webhook table in Snowflake (if it doesn't exist)
-- This matches the schema that Fivetran Webhooks connector would create

USE DATABASE PC_FIVETRAN_DB;
USE SCHEMA webhooks;

-- Create table if it doesn't exist
CREATE TABLE IF NOT EXISTS uber_eats_webhooks (
    event_id VARCHAR,
    job_id VARCHAR,
    event_type VARCHAR,
    body VARIANT,  -- JSON payload stored as VARIANT
    _fivetran_synced TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Grant permissions to the role
GRANT INSERT, SELECT ON TABLE webhooks.uber_eats_webhooks TO ROLE PC_FIVETRAN_ROLE;

-- Verify table exists
SELECT * FROM uber_eats_webhooks LIMIT 0;

