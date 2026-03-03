# Trigger Test Webhook from Uber

## ✅ Deployment Complete

Your enhanced Uber Eats webhook receiver is now deployed and will automatically:
1. Download CSV files when report webhooks arrive
2. Store metadata in `UBER_EATS_REPORTS`
3. Store CSV data in `UBER_EATS_REPORT_DATA`

## 🔗 Current Configuration

**Webhook URL:** `https://uber-eats-webhook-verifier-4eadylqnda-ue.a.run.app/uber-webhook`

**Health Check:** ✅ Connected to Snowflake

## 📋 How to Test & Populate Tables

### Option 1: Generate a New Report via Uber API

If you have API access, trigger a new report:

```bash
# Use your existing access token and store UUID
curl -X POST https://api.uber.com/v1/eats/report \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "FINANCE_SUMMARY_REPORT",
    "start_date": "2026-02-10",
    "end_date": "2026-02-16",
    "store_uuids": ["ad2e72b9-e94d-5cb3-9675-51b7854711f3"]
  }'
```

This will trigger the Uber backend to:
1. Generate the report
2. Send `eats.report.success` webhook to your endpoint
3. Your webhook receiver will download the CSV and populate the tables

### Option 2: Wait for Scheduled Reports

If you set up daily report generation at 7 AM Central:
- Reports will be generated automatically
- Webhooks will be sent automatically
- Tables will be populated automatically

### Option 3: Check Existing Webhooks

The old Fivetran webhook might have recent reports. Check:

```sql
SELECT 
    BODY:"event_id"::VARCHAR AS event_id,
    BODY:"report_metadata":"sections"[0]:"download_url"::VARCHAR AS download_url,
    BODY:"start_time_ms"::BIGINT AS start_time_ms,
    BODY:"end_time_ms"::BIGINT AS end_time_ms
FROM PC_FIVETRAN_DB.WEBHOOKS.UBER_EATS_WEBHOOKS
WHERE EVENT_TYPE = 'eats.report.success'
    AND BODY:"report_metadata":"sections"[0]:"download_url" IS NOT NULL
ORDER BY _FIVETRAN_SYNCED DESC
LIMIT 5;
```

If you find recent reports with valid download URLs (not expired), you could:
1. Test the webhook manually with a sample payload
2. Or wait for the next scheduled report

## 📊 Verify Data After Webhook Arrives

Once a webhook is received, check the tables:

```sql
-- 1. Check reports metadata
SELECT * FROM PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORTS 
ORDER BY _FIVETRAN_SYNCED DESC;

-- 2. Check CSV data rows
SELECT 
    WORKFLOW_ID,
    COUNT(*) AS row_count
FROM PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORT_DATA
GROUP BY WORKFLOW_ID
ORDER BY MAX(_FIVETRAN_SYNCED) DESC;

-- 3. Flatten and view actual CSV data
SELECT 
    r.WORKFLOW_ID,
    r.START_DATE,
    r.END_DATE,
    d.REPORT_DATA:"Store Name"::VARCHAR AS STORE_NAME,
    d.REPORT_DATA:"Order Count"::INT AS ORDER_COUNT,
    d.REPORT_DATA:"Sales (incl. tax)"::FLOAT AS SALES_INCL_TAX,
    d.REPORT_DATA:"Total payout"::FLOAT AS TOTAL_PAYOUT
FROM PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORTS r
JOIN PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORT_DATA d 
    ON r.WORKFLOW_ID = d.WORKFLOW_ID
LIMIT 10;
```

## 🔍 Monitor Webhook Logs

To see real-time webhook activity:

```bash
gcloud run services logs read uber-eats-webhook-verifier \
    --region us-east1 \
    --project cat-database-478219 \
    --limit 50
```

Look for messages like:
- `Received POST /uber-webhook (incoming webhook)`
- `Downloading CSV from URL...`
- `Downloaded 150 CSV rows`
- `✅ MERGE into UBER_EATS_REPORTS`
- `✅ Stored 150 rows in UBER_EATS_REPORT_DATA`

## ⏰ Next Steps

1. **Wait for next report generation** (if you set up daily at 7 AM)
2. **Or trigger a manual report** via API (Option 1 above)
3. **Check tables** after webhook arrives
4. **Verify DBT models** can now read from `UBER_EATS_REPORT_DATA` instead of calling download URLs
