# Uber Eats Webhook - Incremental Updates & Deduplication

## ✅ Deduplication Strategy

Your webhook receiver now handles duplicates properly using **MERGE** (UPSERT) logic.

---

## How It Works

### 1. UBER_EATS_REPORTS Table (Metadata)

**Uses MERGE on WORKFLOW_ID:**

```sql
MERGE INTO UBER_EATS_REPORTS AS target
USING (new_data) AS source
ON target.WORKFLOW_ID = source.WORKFLOW_ID
WHEN MATCHED THEN UPDATE ...
WHEN NOT MATCHED THEN INSERT ...
```

**Behavior:**
- **First time:** Webhook arrives → INSERT new row
- **Duplicate webhook:** Same WORKFLOW_ID arrives → UPDATE existing row (no duplicate!)
- **Result:** Only ONE row per WORKFLOW_ID

**Example:**
```
Day 1: Webhook arrives (workflow_id = "abc-123") → INSERT
Day 2: Same webhook (workflow_id = "abc-123") → UPDATE (no new row)
Day 3: New report (workflow_id = "def-456") → INSERT

Result: 2 rows total (no duplicates)
```

---

### 2. UBER_EATS_REPORT_DATA Table (CSV Rows)

**Uses DELETE + INSERT pattern:**

```sql
-- Step 1: Delete old data for this workflow_id
DELETE FROM UBER_EATS_REPORT_DATA
WHERE WORKFLOW_ID = 'abc-123';

-- Step 2: Insert new CSV rows
INSERT INTO UBER_EATS_REPORT_DATA ...
```

**Behavior:**
- **First time:** Webhook arrives → INSERT 47 CSV rows
- **Duplicate webhook:** Same WORKFLOW_ID arrives → DELETE 47 old rows → INSERT 47 new rows
- **Result:** Always 47 rows for this WORKFLOW_ID (no duplicates)

**Example:**
```
Day 1: Webhook (workflow_id = "abc-123", 47 CSV rows) → INSERT 47 rows
Day 2: Same webhook arrives again → DELETE 47 old → INSERT 47 new → Still 47 rows
Day 3: New report (workflow_id = "def-456", 52 rows) → INSERT 52 rows

Result: 99 rows total (47 + 52, no duplicates)
```

---

## Why This Approach?

### UBER_EATS_REPORTS (Metadata):
- **MERGE** is perfect for metadata
- Updates fields like `DOWNLOADED_AT_UTC` if webhook arrives multiple times
- Primary key: `WORKFLOW_ID` ensures uniqueness

### UBER_EATS_REPORT_DATA (CSV Rows):
- **DELETE + INSERT** is simpler than MERGE for bulk data
- CSV rows don't have a natural primary key (no unique ID per row)
- Ensures exactly the CSV rows from latest webhook

---

## Incremental Updates

### Scenario 1: Daily Reports

**Day 1:**
- Report for Feb 1-7 (workflow_id = "report-week1")
- 47 stores, 47 CSV rows → stored

**Day 2:**
- Report for Feb 8-14 (workflow_id = "report-week2")
- 47 stores, 47 CSV rows → stored
- **Total:** 94 rows (47 + 47, no overlap)

**Day 3:**
- New report for Feb 1-7 regenerated (workflow_id = "report-week1")
- MERGE updates existing record
- DELETE + INSERT replaces old CSV rows
- **Total:** Still 94 rows (no duplicates)

### Scenario 2: Webhook Retry (Uber Resends)

**If Uber doesn't get 200 OK, they retry up to 7 times:**

**Attempt 1:**
- Webhook arrives → stored in Snowflake → Return 200

**Attempt 2 (retry):**
- Same webhook arrives again
- **UBER_EATS_REPORTS:** MERGE updates (no duplicate)
- **UBER_EATS_REPORT_DATA:** DELETE old + INSERT new (no duplicates)
- Return 200

**Result:** No duplicates even with retries!

---

## DBT Incremental Models

Your DBT models can use standard incremental patterns:

### Option 1: Process New Reports Only

```sql
{{
  config(
    materialized='incremental',
    unique_key='workflow_id'
  )
}}

SELECT 
  r.WORKFLOW_ID,
  r.START_DATE,
  r.END_DATE,
  d.REPORT_DATA:"Store Name"::VARCHAR AS STORE_NAME,
  d.REPORT_DATA:"Total payout"::FLOAT AS TOTAL_PAYOUT,
  r._FIVETRAN_SYNCED
FROM PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORTS r
JOIN PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORT_DATA d
  ON r.WORKFLOW_ID = d.WORKFLOW_ID
WHERE r.DOWNLOADED_AT_UTC IS NOT NULL

{% if is_incremental() %}
  -- Only process new reports
  AND r._FIVETRAN_SYNCED > (SELECT MAX(_FIVETRAN_SYNCED) FROM {{ this }})
{% endif %}
```

### Option 2: Add Processed Flag

Add a column to track what DBT has processed:

```sql
-- Add processed flag
ALTER TABLE PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORTS 
ADD COLUMN DBT_PROCESSED BOOLEAN DEFAULT FALSE;

-- DBT model: Only process unprocessed
SELECT ... 
FROM UBER_EATS_REPORTS
WHERE DBT_PROCESSED = FALSE;

-- After processing:
UPDATE UBER_EATS_REPORTS 
SET DBT_PROCESSED = TRUE
WHERE WORKFLOW_ID IN (...);
```

---

## Summary

✅ **UBER_EATS_REPORTS:** MERGE on WORKFLOW_ID (no duplicate reports)  
✅ **UBER_EATS_REPORT_DATA:** DELETE + INSERT per workflow_id (no duplicate CSV rows)  
✅ **Idempotent:** Same webhook twice = same result  
✅ **Incremental:** DBT can track which reports are processed  
✅ **Same as Fivetran:** Standard incremental pattern  

**Result:** Clean data, no duplicates, incremental updates work perfectly!
