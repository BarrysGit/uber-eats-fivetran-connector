-- Enhanced Uber Eats Webhook Tables
-- Run this in Snowflake to create/update tables

USE DATABASE PC_FIVETRAN_DB;
USE SCHEMA webhooks;

-- 1. Enhanced webhook metadata table
CREATE TABLE IF NOT EXISTS uber_eats_webhooks (
    event_id VARCHAR,
    event_type VARCHAR,
    report_type VARCHAR,                    -- 'FINANCE_SUMMARY_REPORT', etc.
    start_time_ms BIGINT,                   -- Report start timestamp (Unix ms)
    end_time_ms BIGINT,                     -- Report end timestamp (Unix ms)
    download_urls VARIANT,                  -- Array of download URLs from sections
    csv_downloaded BOOLEAN DEFAULT FALSE,   -- Has CSV been downloaded?
    csv_row_count INT,                      -- Total rows downloaded
    body VARIANT,                           -- Original full payload
    _fivetran_synced TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- 2. CSV data table (downloaded and parsed CSV rows)
CREATE TABLE IF NOT EXISTS uber_eats_reports_csv (
    report_id VARCHAR,              -- event_id from webhook
    section_id VARCHAR,             -- section_id from report_metadata
    report_type VARCHAR,            -- FINANCE_SUMMARY_REPORT
    start_date DATE,                -- Converted from start_time_ms
    end_date DATE,                  -- Converted from end_time_ms
    csv_data VARIANT,               -- CSV rows as JSON array
    row_count INT,                  -- Number of rows in CSV
    downloaded_at TIMESTAMP_NTZ,    -- When CSV was downloaded
    processed BOOLEAN DEFAULT FALSE -- For DBT to track processing
);

-- Grant permissions
GRANT INSERT, SELECT, UPDATE ON TABLE uber_eats_webhooks TO ROLE PC_FIVETRAN_ROLE;
GRANT INSERT, SELECT, UPDATE ON TABLE uber_eats_reports_csv TO ROLE PC_FIVETRAN_ROLE;

-- Verify tables exist
SELECT 'uber_eats_webhooks' AS table_name, COUNT(*) AS row_count FROM uber_eats_webhooks
UNION ALL
SELECT 'uber_eats_reports_csv', COUNT(*) FROM uber_eats_reports_csv;

-- Sample query to view downloaded reports
SELECT 
    event_id,
    report_type,
    TO_DATE(start_time_ms / 1000) AS start_date,
    TO_DATE(end_time_ms / 1000) AS end_date,
    csv_downloaded,
    csv_row_count,
    _fivetran_synced
FROM uber_eats_webhooks
WHERE event_type = 'eats.report.success'
ORDER BY _fivetran_synced DESC;

-- Sample query to view CSV data
SELECT 
    report_id,
    section_id,
    report_type,
    start_date,
    end_date,
    row_count,
    processed,
    downloaded_at
FROM uber_eats_reports_csv
ORDER BY downloaded_at DESC;

-- Query to flatten CSV data for DBT processing
SELECT 
    r.report_id,
    r.report_type,
    r.start_date,
    r.end_date,
    f.value AS row_data  -- Each CSV row
FROM uber_eats_reports_csv r,
LATERAL FLATTEN(input => r.csv_data) f
WHERE r.processed = FALSE
LIMIT 10;
