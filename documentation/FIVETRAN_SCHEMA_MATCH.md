# Uber Eats Webhook - Match Fivetran Schema

## Goal

Replicate Fivetran's exact table structure so DBT models work without changes:

### Fivetran Tables:
1. **`UBER_EATS_STORES`** - Store information (name, address, etc.)
2. **`UBER_EATS_REPORTS`** - Report metadata (workflow_id, download_url, dates, status)
3. **`UBER_EATS_REPORT_DATA`** - Actual CSV data from reports

## Revised Approach

### Option 1: Store Webhook → DBT Downloads CSV (Like Fivetran)

**Tables:**
```sql
-- Stores table (populated via Uber Stores API separately)
CREATE TABLE UBER_EATS_STORES (
    STORE_ID VARCHAR PRIMARY KEY,
    NAME VARCHAR,
    LOCATION_ADDRESS VARCHAR,
    LOCATION_CITY VARCHAR,
    LOCATION_STATE VARCHAR,
    LOCATION_POSTAL_CODE VARCHAR,
    LOCATION_COUNTRY VARCHAR,
    LOCATION_LATITUDE FLOAT,
    LOCATION_LONGITUDE FLOAT,
    TIMEZONE VARCHAR,
    STATUS VARCHAR,
    WEB_URL VARCHAR,
    RAW_HERO_URL VARCHAR,
    AVG_PREP_TIME INT,
    POS_DATA_INTEGRATION_ENABLED BOOLEAN,
    LOCATION_ADDRESS_2 VARCHAR,
    _FIVETRAN_SYNCED TIMESTAMP_NTZ,
    _FIVETRAN_DELETED BOOLEAN DEFAULT FALSE
);

-- Reports metadata (from webhooks)
CREATE TABLE UBER_EATS_REPORTS (
    WORKFLOW_ID VARCHAR PRIMARY KEY,
    REPORT_TYPE VARCHAR,
    STATUS VARCHAR,
    START_DATE DATE,
    END_DATE DATE,
    STORE_UUIDS VARIANT,  -- JSON array
    DOWNLOAD_URL VARCHAR,
    CREATED_AT_UTC TIMESTAMP_NTZ,
    DOWNLOADED_AT_UTC TIMESTAMP_NTZ,
    _FIVETRAN_SYNCED TIMESTAMP_NTZ,
    _FIVETRAN_DELETED BOOLEAN DEFAULT FALSE
);

-- Report data (CSV rows)
CREATE TABLE UBER_EATS_REPORT_DATA (
    WORKFLOW_ID VARCHAR,
    STORE_NAME VARCHAR,
    SHOP_ID VARCHAR,
    STORE_ID VARCHAR,
    ORDER_COUNT INT,
    -- All other CSV columns...
    _FIVETRAN_SYNCED TIMESTAMP_NTZ,
    _FIVETRAN_DELETED BOOLEAN DEFAULT FALSE
);
```

**Webhook Receiver:**
- Receives `eats.report.success` webhook
- Extracts metadata
- Stores in `UBER_EATS_REPORTS` with:
  - `workflow_id` = `event_id`
  - `download_url` = first section's download_url
  - `status` = 'COMPLETED'
  - `start_date` = from `start_time_ms`
  - `end_date` = from `end_time_ms`

**DBT Workflow:**
1. Query `UBER_EATS_REPORTS` for new reports
2. Download CSV from `download_url`
3. Parse and load into `UBER_EATS_REPORT_DATA`
4. Mark as processed

---

## Implementation

I'll update the webhook receiver to:
1. Store webhook in `UBER_EATS_REPORTS` table (matching Fivetran schema)
2. Extract download_url, dates, etc. into proper columns
3. DBT can then download CSV and populate `UBER_EATS_REPORT_DATA`

This way:
- ✅ DBT models work with minimal changes
- ✅ Same table structure as Fivetran
- ✅ Your existing DBT queries still work

Want me to update the code to match this structure?
