# Complete Uber Eats Integration (No Fivetran)

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     COMPLETE END-TO-END FLOW                     │
└─────────────────────────────────────────────────────────────────┘

   ⏰ Cloud Scheduler                    🌐 Uber Eats API
   (Daily 7 AM Central)                      
         │                                      
         │ triggers                             
         ▼                                      
   ☁️  Cloud Run Job                            
   (report_generator.py)                        
         │                                      
         ├─────────► 🏪 Stores API ──────┐     
         │          (GET /stores)          │     
         │                                 │     
         │                                 ▼     
         │                          💾 SNOWFLAKE
         │                          UBER_EATS_STORES
         │                                       
         ├─────────► 📊 Reports API              
         │          (POST /report)                
         │          ↓                             
         │       workflow_id                      
         │          ↓                             
         │    ⏳ Report generation...             
         │          ↓                             
         │    📬 Webhook sent                     
         │          ↓                             
         ▼          ▼                             
   ☁️  Cloud Run Service                         
   (webhook receiver)                            
   main_snowflake.py                             
         │                                       
         ├─────► 📥 Download CSV                 
         │       from download_url               
         │                                       
         └─────► 💾 SNOWFLAKE                    
                 ├─ UBER_EATS_REPORTS (metadata)
                 └─ UBER_EATS_REPORT_DATA (CSV rows)
```

## 📋 Components

### 1. **Cloud Run Job** (`report_generator.py`)
**Runs:** Daily at 7 AM Central Time (via Cloud Scheduler)

**Does:**
1. Gets OAuth token from Uber
2. Fetches all stores → stores in `UBER_EATS_STORES`
3. Triggers report for all stores → gets `workflow_id`
4. Exits (webhook will arrive later)

**Tables Written:**
- `PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_STORES`

---

### 2. **Cloud Run Service** (`main_snowflake.py`)
**Runs:** Always available (webhook endpoint)

**Does:**
1. Receives `eats.report.success` webhook
2. Downloads CSV from `download_url` (before it expires)
3. Parses CSV rows
4. Stores metadata + CSV data in Snowflake

**Tables Written:**
- `PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORTS` (1 row per report)
- `PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORT_DATA` (many rows)

---

### 3. **Cloud Scheduler**
**Schedule:** Daily at 7 AM Central Time
**Cron:** `0 13 * * *` (America/Chicago timezone)
**Action:** Triggers Cloud Run Job

---

## 🗄️ Snowflake Tables

### `UBER_EATS_STORES`
```sql
STORE_ID (PK)           -- Store UUID
NAME                    -- Store name
LOCATION_ADDRESS        -- Address
LOCATION_CITY           
LOCATION_STATE          
TIMEZONE                
STATUS                  -- Active/Inactive
RAW_DATA (VARIANT)      -- Full JSON from API
_FIVETRAN_SYNCED        
_FIVETRAN_DELETED       
```

### `UBER_EATS_REPORTS`
```sql
WORKFLOW_ID (PK)        -- Report workflow UUID
REPORT_TYPE             -- FINANCE_SUMMARY_REPORT
STATUS                  -- COMPLETED
START_DATE              -- Report start date
END_DATE                -- Report end date
STORE_UUIDS (VARIANT)   -- Array of store IDs
DOWNLOAD_URL            -- CSV download URL
CREATED_AT_UTC          -- When report was created
DOWNLOADED_AT_UTC       -- When CSV was downloaded
_FIVETRAN_SYNCED        
_FIVETRAN_DELETED       
```

### `UBER_EATS_REPORT_DATA`
```sql
WORKFLOW_ID             -- Links to UBER_EATS_REPORTS
REPORT_DATA (VARIANT)   -- Full CSV row as JSON
                        -- Contains: Store Name, Order Count,
                        -- Sales, Fees, Payout, etc.
_FIVETRAN_SYNCED        
_FIVETRAN_DELETED       
```

---

## 🚀 Deployment Commands

### Deploy Everything (Job + Scheduler + Webhook Receiver)
```bash
cd /Users/amreshsingh/Documents/GitHub/Custom_connectors/uber-eats/webhook-verifier-python
./deploy_complete_solution.sh
```

This will:
1. Build Docker image for the job
2. Deploy Cloud Run Job
3. Test the job manually (first run)
4. Create Cloud Scheduler for daily execution
5. Webhook receiver is already deployed

---

## 🔍 Monitoring & Verification

### Check Job Logs
```bash
# List recent job executions
gcloud run jobs executions list uber-eats-report-generator \
  --region us-east1 \
  --project cat-database-478219

# View logs from latest execution
gcloud run jobs executions describe <EXECUTION_NAME> \
  --region us-east1 \
  --project cat-database-478219
```

### Check Scheduler Status
```bash
gcloud scheduler jobs describe uber-eats-daily-reports \
  --location us-east1 \
  --project cat-database-478219
```

### Check Webhook Receiver Logs
```bash
gcloud run services logs read uber-eats-webhook-verifier \
  --region us-east1 \
  --project cat-database-478219 \
  --limit 50
```

### Verify Data in Snowflake
```sql
-- Check stores
SELECT COUNT(*), MAX(_FIVETRAN_SYNCED) 
FROM PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_STORES;

-- Check reports
SELECT * FROM PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORTS 
ORDER BY _FIVETRAN_SYNCED DESC;

-- Check CSV data
SELECT 
    WORKFLOW_ID, 
    COUNT(*) AS rows 
FROM PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORT_DATA 
GROUP BY WORKFLOW_ID;

-- View actual report data
SELECT 
    r.WORKFLOW_ID,
    r.START_DATE,
    r.END_DATE,
    d.REPORT_DATA:"Store Name"::VARCHAR AS store_name,
    d.REPORT_DATA:"Order Count"::INT AS orders,
    d.REPORT_DATA:"Sales (incl. tax)"::FLOAT AS sales,
    d.REPORT_DATA:"Total payout"::FLOAT AS payout
FROM PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORTS r
JOIN PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORT_DATA d 
    ON r.WORKFLOW_ID = d.WORKFLOW_ID
ORDER BY r.START_DATE DESC, store_name
LIMIT 100;
```

---

## 📅 Timeline (Example)

**7:00 AM Central** → Cloud Scheduler triggers job
**7:00-7:02 AM** → Job fetches stores, triggers report
**7:02 AM** → Job completes, webhook pending
**7:05-7:15 AM** → Uber generates report
**7:15 AM** → Webhook sent to receiver
**7:15 AM** → Receiver downloads CSV, stores in Snowflake
**7:15 AM** → ✅ Data available in `UBER_EATS_REPORT_DATA`

---

## 🎯 Benefits vs Fivetran

| Feature | Fivetran | This Solution |
|---------|----------|---------------|
| **Cost** | $$$ per month | Cloud Run costs only (~$5/month) |
| **Customization** | Limited | Full control |
| **CSV Download** | Manual in DBT | Automatic in webhook |
| **Store Data** | Separate connector | Same job |
| **URL Expiration** | Risk | No risk (immediate download) |
| **Dependencies** | External service | Self-contained |
| **Debugging** | Hard | Full logs access |

---

## ✅ Next Steps After Deployment

1. **Wait for first scheduled run** (7 AM Central tomorrow)
2. **Or trigger manually:**
   ```bash
   gcloud run jobs execute uber-eats-report-generator \
     --region us-east1 --project cat-database-478219 --wait
   ```
3. **Check data in Snowflake** (queries above)
4. **Update DBT models** to read from `UBER_EATS_REPORT_DATA` directly
5. **Decommission Fivetran connector** ✂️

---

## 🆘 Troubleshooting

### Job fails with "No stores found"
- Check UBER_CLIENT_ID and UBER_CLIENT_SECRET secrets
- Verify OAuth token generation in logs

### Webhook not arriving
- Check webhook receiver is deployed: `gcloud run services list`
- Verify URL in Uber Developer Dashboard
- Check job logs for workflow_id

### CSV download fails
- URL might be expired (check timing)
- Check webhook receiver logs for error details

### Snowflake write fails
- Verify SNOWFLAKE_WAREHOUSE secret = `SCRAPPER_WH`
- Check SNOWFLAKE_PRIVATE_KEY secret exists
- Verify tables exist (run CREATE_TABLES_SIMPLE.sql)
