# Uber Eats Webhook Enhancement Plan

## Current Workflow (As-Is)

1. **Uber sends webhook** → `eats.report.success` event
2. **Your webhook receiver** stores the raw payload in Snowflake (`uber_eats_webhooks` table)
3. **DBT job** queries Snowflake, finds new webhooks, calls Uber API to get download URLs
4. **DBT job** downloads CSV from URL
5. **DBT job** parses CSV and updates final table

## Problem with Current Approach

- DBT has to call the Uber API again to get download URLs
- Multiple round trips
- More API calls = more quota usage

---

## Proposed Enhanced Workflow (To-Be)

### Option 1: Extract Download URLs in Webhook (Recommended)

**Changes to webhook receiver:**

1. **Parse the `download_urls`** from webhook payload
2. **Store them as additional columns** for easy DBT access
3. **Optionally download CSV immediately** and store content in Snowflake

**Benefits:**
- DBT doesn't need to call Uber API again
- Download URLs are immediately available in Snowflake
- Faster processing
- Fewer API calls

**New table schema:**
```sql
CREATE TABLE uber_eats_webhooks (
    event_id VARCHAR,
    event_type VARCHAR,
    workflow_id VARCHAR,           -- NEW: For tracking report generation
    report_type VARCHAR,            -- NEW: e.g., 'FINANCE_SUMMARY_REPORT'
    download_urls VARIANT,          -- NEW: JSON array of download URLs
    download_status VARCHAR,        -- NEW: 'pending', 'downloaded', 'failed'
    csv_content VARIANT,            -- NEW: Optionally store downloaded CSV as JSON
    body VARIANT,                   -- Original full payload
    _fivetran_synced TIMESTAMP_NTZ
);
```

**DBT workflow becomes:**
```sql
-- Step 1: Find new reports
SELECT 
    event_id,
    workflow_id,
    report_type,
    download_urls,
    download_status
FROM uber_eats_webhooks
WHERE event_type = 'eats.report.success'
  AND download_status = 'pending'
```

Then DBT can directly download from `download_urls` without calling Uber API.

---

### Option 2: Download CSV in Webhook Receiver (Even Better)

**Webhook receiver:**
1. Receives `eats.report.success` webhook
2. Extracts `download_urls` from payload
3. **Immediately downloads CSV** from each URL
4. **Parses CSV** and stores in Snowflake
5. Marks as `download_status = 'downloaded'`

**Benefits:**
- DBT only reads pre-downloaded data (no HTTP calls)
- Fastest processing
- CSV is archived in Snowflake (audit trail)
- Handles transient download failures with retries

**DBT workflow becomes:**
```sql
-- Just read the data
SELECT * FROM uber_eats_reports_raw
WHERE processed = FALSE
```

---

## Implementation Options

### Option 1A: Enhance Webhook to Extract URLs Only

**Minimal changes:**
- Parse `download_urls` from payload
- Store as separate column
- DBT downloads CSV later

**Code changes:**
```python
def store_webhook_in_snowflake(payload: Dict[str, Any], headers: Dict[str, str]) -> bool:
    # Extract fields
    event_id = payload.get("event_id", "")
    event_type = payload.get("event_type", "")
    workflow_id = payload.get("workflow_id", "")
    
    # NEW: Extract download URLs
    download_urls = payload.get("download_urls", [])
    report_type = payload.get("report_type", "")
    
    insert_query = f"""
    INSERT INTO {SNOWFLAKE_SCHEMA}.{SNOWFLAKE_TABLE} (
        event_id,
        event_type,
        workflow_id,
        report_type,
        download_urls,
        download_status,
        body,
        _fivetran_synced
    ) VALUES (
        %s, %s, %s, %s, PARSE_JSON(%s), %s, PARSE_JSON(%s), %s
    )
    """
    
    cursor.execute(insert_query, (
        event_id,
        event_type,
        workflow_id,
        report_type,
        json.dumps(download_urls),
        'pending',
        body_json,
        synced_at
    ))
```

### Option 1B: Download CSV in Webhook Receiver

**More robust:**
- Webhook downloads CSV immediately
- Stores CSV content in Snowflake
- DBT just processes the data

**Code changes:**
```python
import requests
import csv
import io

def download_and_store_csv(download_urls: list, workflow_id: str, conn) -> bool:
    """Download CSV from Uber and store in Snowflake"""
    for url in download_urls:
        try:
            # Download CSV
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            
            # Parse CSV
            csv_content = response.text
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            rows = list(csv_reader)
            
            # Store in Snowflake (as JSON for now)
            cursor = conn.cursor()
            insert_query = f"""
            INSERT INTO uber_eats_reports_raw (
                workflow_id,
                download_url,
                csv_data,
                row_count,
                downloaded_at
            ) VALUES (%s, %s, PARSE_JSON(%s), %s, %s)
            """
            
            cursor.execute(insert_query, (
                workflow_id,
                url,
                json.dumps(rows),
                len(rows),
                datetime.now(timezone.utc)
            ))
            
            logger.info(f"Downloaded and stored CSV: {len(rows)} rows from {url}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download CSV from {url}: {e}")
            return False
```

---

## Recommendation

**Start with Option 1A** (Extract URLs):
- Quick to implement
- Low risk
- DBT can still download CSV (you control retry logic)

**Then upgrade to Option 1B** (Download in webhook):
- More robust
- Faster DBT processing
- Better error handling in webhook receiver

---

## Next Steps

1. **Test with real webhook payload** - Need to see actual structure of `eats.report.success`
2. **Update Snowflake table** - Add new columns
3. **Update webhook receiver** - Extract download URLs
4. **Test DBT workflow** - Verify it can read URLs and download CSV

Would you like me to:
1. Update the webhook receiver code to extract download URLs?
2. Create the enhanced Snowflake table schema?
3. Both?
