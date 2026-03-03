# Uber Eats API - What We're Using

## 🔐 Authentication

### OAuth 2.0 Client Credentials Flow
**Endpoint:** `https://login.uber.com/oauth/v2/token`

**Request:**
```bash
POST https://login.uber.com/oauth/v2/token
Content-Type: application/x-www-form-urlencoded

client_id=ypYKCyBCZRYqzkJRfUmE7vBPGxrru5yk
client_secret=i7ET6du4qb_paToesQ9Ue9ruEnfsZyvUVf1jjjrY
grant_type=client_credentials
scope=eats.report eats.store
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 2592000,
  "scope": "eats.report eats.store"
}
```

**Current Status:** ❌ Returns `403 Forbidden` (needs investigation)

---

## 📊 API 1: Stores API

### Get All Stores
**Endpoint:** `GET https://api.uber.com/v1/eats/stores`

**Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Query Parameters:**
```
limit: 100 (max per page)
page_token: {next_page_token} (for pagination)
```

**Response:**
```json
{
  "stores": [
    {
      "id": "ad2e72b9-e94d-5cb3-9675-51b7854711f3",
      "name": "Barry's Bootcamp - Location Name",
      "location": {
        "address": "123 Main St",
        "city": "New York",
        "state": "NY",
        "postal_code": "10001",
        "country": "US",
        "latitude": 40.7128,
        "longitude": -74.0060
      },
      "timezone": "America/New_York",
      "status": "ACTIVE",
      "web_url": "https://www.ubereats.com/store/...",
      "avg_prep_time": 15,
      "pos_data_integration_enabled": true
    }
    // ... more stores
  ],
  "next_page_token": "abc123..." // Present if more pages exist
}
```

**What We Get:**
- Store UUID (unique identifier)
- Store name and location details
- Timezone (important for report date ranges)
- Status (ACTIVE/INACTIVE)
- POS integration status

**What We Store:**
→ Table: `PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_STORES`

---

## 📈 API 2: Reports API

### Trigger Report Generation
**Endpoint:** `POST https://api.uber.com/v1/eats/report`

**Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "report_type": "FINANCE_SUMMARY_REPORT",
  "start_date": "2026-02-10",
  "end_date": "2026-02-16",
  "store_uuids": [
    "ad2e72b9-e94d-5cb3-9675-51b7854711f3",
    "another-store-uuid-here"
  ]
}
```

**Response:**
```json
{
  "workflow_uuid": "2fc42be9-60fe-4752-999e-38ace2f7ca82_5fb36ac2-fbce-4c4d-aaf6-efb99b069ee8",
  "status": "PROCESSING"
}
```

**What We Get:**
- `workflow_uuid` (used to track the report)
- Status (PROCESSING → will become COMPLETED)

**What Happens Next:**
1. Uber generates the report asynchronously (takes 5-15 minutes)
2. When ready, Uber sends a webhook to your endpoint
3. Webhook contains the `download_url` for the CSV

---

## 📬 API 3: Webhooks (Incoming)

### Event: `eats.report.success`
**Endpoint:** Your webhook receiver receives this

**Webhook Payload:**
```json
{
  "event_id": "2fc42be9-60fe-4752-999e-38ace2f7ca82_5fb36ac2-fbce-4c4d-aaf6-efb99b069ee8",
  "event_type": "eats.report.success",
  "job_id": "2fc42be9-60fe-4752-999e-38ace2f7ca82_5fb36ac2-fbce-4c4d-aaf6-efb99b069ee8",
  "report_type": "FINANCE_SUMMARY_REPORT",
  "start_time_ms": 1770336000000,
  "end_time_ms": 1770940799000,
  "report_metadata": {
    "sections": [
      {
        "section_id": "5fb36ac2-fbce-4c4d-aaf6-efb99b069ee8",
        "content_type": "text/csv",
        "download_url": "https://tbgs-static.uber.com/prod/ue_money/.../report.csv?Expires=1771101065&KeyName=destiny_keysets&Signature=82-Sk_7Z..."
      }
    ]
  },
  "webhook_meta": {
    "client_id": "ypYKCyBCZRYqzkJRfUmE7vBPGxrru5yk",
    "webhook_config_id": "restaurant-financial-data.road-report-completion",
    "webhook_msg_timestamp": 1771014665,
    "webhook_msg_uuid": "297f132a-c357-495b-8b2e-5ee859625977"
  }
}
```

**Headers:**
```
X-Uber-Signature: {hmac_sha256_signature}
Content-Type: application/json
```

**What We Extract:**
- `event_id` → Used as `WORKFLOW_ID`
- `report_type` → FINANCE_SUMMARY_REPORT
- `start_time_ms` / `end_time_ms` → Convert to DATE
- `download_url` → CSV download link (expires in ~24 hours)

**What We Do:**
1. Download CSV from `download_url`
2. Parse CSV rows
3. Store in Snowflake

---

## 📥 API 4: CSV Download (via download_url)

### Download Report CSV
**Endpoint:** URL from webhook (signed, temporary)

**Example URL:**
```
https://tbgs-static.uber.com/prod/ue_money/a2e9406a-ef24-4103-814e-b083a159a8c8/5fb36ac2-fbce-4c4d-aaf6-efb99b069ee8-united_states.csv?Expires=1771101065&KeyName=destiny_keysets&Signature=82-Sk_7Zfy2XzcZqmqdCmCFO9YqKd02ssMDyyN04XY270BHfgeiCD0IOtTXBkJc2UkIU9zwVYvTWnJr7RGtmCw
```

**Request:**
```bash
GET {download_url}
```

**Response:** CSV file with columns:
```csv
Store Name,Shop ID,Store ID,Order Count,Count of Misc payment,Sales (excl. tax),Tax on Sales,Sales (incl. tax),Order Error Adjustments,Tax on Order Error Adjustments,Order Error Adjustments (incl. tax),Price adjustments (excl. tax),Tax on Price Adjustments,Price Adjustments (incl. tax),Offers on items (incl. tax),Tax On Offers on items,Delivery Offer Redemptions (incl. tax),Tax On Delivery Offer Redemptions,Offer Redemption Fee,Marketing Adjustment,Bag Fee,Marketplace Fee,Tax on Marketplace Fee,Delivery Network Fee,Tax on Delivery Network Fee,Order Processing Fee,Total Sales after Adjustments (incl tax),Capital payments,Other payments,Marketplace Facilitator Tax Adjustment,Marketplace Facilitator Tax,Backup Withholding Tax,Total payout,Payout Date,Payout reference ID
```

**Example Row:**
```csv
Barry's Bootcamp NYC,SHOP123,ad2e72b9-e94d-5cb3-9675-51b7854711f3,150,0,12500.00,1000.00,13500.00,0.00,0.00,0.00,-200.00,-16.00,-216.00,-300.00,-24.00,-50.00,-4.00,10.00,0.00,25.00,2025.00,162.00,450.00,36.00,75.00,12905.00,0.00,0.00,0.00,0.00,0.00,10855.00,2026-02-16,PAY_REF_12345
```

**What We Store:**
→ Table: `PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORT_DATA`
→ Each CSV row stored as JSON in `REPORT_DATA` column

---

## 🗄️ Data Storage Summary

### Flow: API → Snowflake

```
1. Stores API
   ↓
   GET /v1/eats/stores
   ↓
   {stores: [...]}
   ↓
   UBER_EATS_STORES table
   (STORE_ID, NAME, LOCATION_*, TIMEZONE, STATUS, RAW_DATA)

2. Reports API
   ↓
   POST /v1/eats/report
   ↓
   {workflow_uuid: "abc123..."}
   ↓
   (wait for webhook...)

3. Webhook Received
   ↓
   eats.report.success
   ↓
   {download_url: "https://..."}
   ↓
   UBER_EATS_REPORTS table
   (WORKFLOW_ID, REPORT_TYPE, START_DATE, END_DATE, DOWNLOAD_URL, DOWNLOADED_AT_UTC)

4. CSV Download
   ↓
   GET {download_url}
   ↓
   CSV with 35 columns
   ↓
   UBER_EATS_REPORT_DATA table
   (WORKFLOW_ID, REPORT_DATA as JSON)
```

---

## 📋 CSV Columns (FINANCE_SUMMARY_REPORT)

The CSV contains **35 columns** with financial data:

### Store Information
- Store Name
- Shop ID
- Store ID (UUID)

### Order Metrics
- Order Count
- Count of Misc payment

### Sales
- Sales (excl. tax)
- Tax on Sales
- Sales (incl. tax)

### Adjustments
- Order Error Adjustments
- Tax on Order Error Adjustments
- Order Error Adjustments (incl. tax)
- Price adjustments (excl. tax)
- Tax on Price Adjustments
- Price Adjustments (incl. tax)

### Offers & Promotions
- Offers on items (incl. tax)
- Tax On Offers on items
- Delivery Offer Redemptions (incl. tax)
- Tax On Delivery Offer Redemptions
- Offer Redemption Fee
- Marketing Adjustment

### Fees
- Bag Fee
- Marketplace Fee
- Tax on Marketplace Fee
- Delivery Network Fee
- Tax on Delivery Network Fee
- Order Processing Fee

### Totals
- Total Sales after Adjustments (incl tax)
- Capital payments
- Other payments

### Taxes
- Marketplace Facilitator Tax Adjustment
- Marketplace Facilitator Tax
- Backup Withholding Tax

### Payout
- Total payout
- Payout Date
- Payout reference ID

---

## 🔄 Complete Data Flow

```
┌─────────────────────────────────────────────────────────┐
│                    DATA FLOW DIAGRAM                     │
└─────────────────────────────────────────────────────────┘

1. STORES API
   GET /v1/eats/stores
   ↓
   Response: {stores: [store1, store2, ...]}
   ↓
   Store in Snowflake: UBER_EATS_STORES
   (Store IDs, Names, Locations, Timezones)

2. REPORTS API
   POST /v1/eats/report
   Body: {report_type, start_date, end_date, store_uuids}
   ↓
   Response: {workflow_uuid: "abc123..."}
   ↓
   (Uber generates report asynchronously - takes 5-15 min)

3. WEBHOOK RECEIVED
   POST /uber-webhook
   Body: {event_type: "eats.report.success", download_url: "..."}
   ↓
   Extract: workflow_id, download_url, dates
   ↓
   Store metadata: UBER_EATS_REPORTS

4. CSV DOWNLOAD
   GET {download_url}
   ↓
   Response: CSV file (text/csv)
   ↓
   Parse CSV rows (35 columns per row)
   ↓
   Store data: UBER_EATS_REPORT_DATA
   (Each row as JSON in REPORT_DATA column)

5. DBT MODELS (Your Next Step)
   SELECT from UBER_EATS_REPORT_DATA
   ↓
   Flatten JSON: REPORT_DATA:"Store Name", REPORT_DATA:"Sales (incl. tax)", etc.
   ↓
   Create analytics tables
```

---

## 🎯 What Each API Gives You

### Stores API → Store Information
**Purpose:** Get list of all your stores/locations

**Use Case:**
- Know which stores exist
- Get store UUIDs for report generation
- Map store IDs to names/locations in analytics

**Data:**
- Store metadata (name, address, timezone)
- Store status (active/inactive)
- POS integration status

### Reports API → Trigger Report Generation
**Purpose:** Request a financial report for specific date range and stores

**Use Case:**
- Generate daily/weekly financial reports
- Get sales data for specific time periods
- Trigger reports programmatically

**Data:**
- Returns workflow_uuid (to track the report)
- Actual report data comes via webhook later

### Webhooks → Report Completion Notification
**Purpose:** Notify you when report is ready with download link

**Use Case:**
- Know when report generation is complete
- Get temporary download URL for CSV
- Trigger automated data ingestion

**Data:**
- Workflow ID (matches the one from Reports API)
- Download URL (temporary, expires in ~24 hours)
- Report metadata (type, date range, sections)

### CSV Download → Actual Financial Data
**Purpose:** Get the actual report data (sales, fees, payouts)

**Use Case:**
- Download detailed financial data
- Ingest into data warehouse
- Build analytics and dashboards

**Data:**
- 35 columns of financial metrics per store
- Order counts, sales, taxes, fees, payouts
- Payout dates and reference IDs

---

## 📊 Example: Complete Flow

### Step 1: Get Stores
```bash
curl -X GET "https://api.uber.com/v1/eats/stores?limit=100" \
  -H "Authorization: Bearer {token}"
```

**Result:** 
- 50 stores returned
- Store UUIDs: `[uuid1, uuid2, ..., uuid50]`
- Stored in `UBER_EATS_STORES`

### Step 2: Trigger Report
```bash
curl -X POST "https://api.uber.com/v1/eats/report" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "FINANCE_SUMMARY_REPORT",
    "start_date": "2026-02-10",
    "end_date": "2026-02-16",
    "store_uuids": ["uuid1", "uuid2", ..., "uuid50"]
  }'
```

**Result:**
- `workflow_uuid: "abc123..."`
- Report is being generated (takes 5-15 min)

### Step 3: Wait for Webhook
```
(5-15 minutes later)

POST https://your-webhook-url.run.app/uber-webhook
{
  "event_id": "abc123...",
  "event_type": "eats.report.success",
  "report_metadata": {
    "sections": [{
      "download_url": "https://tbgs-static.uber.com/prod/ue_money/.../report.csv?..."
    }]
  }
}
```

**Result:**
- Webhook received by your receiver
- Metadata stored in `UBER_EATS_REPORTS`

### Step 4: Download CSV
```bash
curl "https://tbgs-static.uber.com/prod/ue_money/.../report.csv?..."
```

**Result:**
- CSV file downloaded (text/csv)
- 50 rows (one per store)
- 35 columns per row
- Parsed and stored in `UBER_EATS_REPORT_DATA`

### Step 5: Query Data
```sql
SELECT 
    r.START_DATE,
    r.END_DATE,
    d.REPORT_DATA:"Store Name"::VARCHAR AS store_name,
    d.REPORT_DATA:"Order Count"::INT AS orders,
    d.REPORT_DATA:"Sales (incl. tax)"::FLOAT AS sales,
    d.REPORT_DATA:"Marketplace Fee"::FLOAT AS marketplace_fee,
    d.REPORT_DATA:"Total payout"::FLOAT AS payout
FROM PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORTS r
JOIN PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_REPORT_DATA d 
    ON r.WORKFLOW_ID = d.WORKFLOW_ID
WHERE r.START_DATE = '2026-02-10'
```

**Result:**
- Financial data for all stores for the week
- Ready for analytics, dashboards, DBT models

---

## 🔑 Key Concepts

### Workflow UUID
- Unique identifier for each report generation request
- Used to link:
  - Report trigger (Reports API)
  - Webhook notification (eats.report.success)
  - CSV data (UBER_EATS_REPORT_DATA)

### Download URL Expiration
- URLs expire in ~24 hours
- **Critical:** Must download immediately when webhook arrives
- Our webhook receiver does this automatically

### Report Types
- `FINANCE_SUMMARY_REPORT` - Daily financial summary (what we use)
- Other types might be available (check Uber docs)

### Date Ranges
- `start_date` and `end_date` are inclusive
- Timezone-aware (uses store's timezone)
- Typically: weekly reports (7 days)

---

## 🚨 Current Issues

### OAuth 403 Error
**Problem:** Cannot get access token via client credentials flow

**Error:**
```
403 Client Error: Forbidden for url: https://login.uber.com/oauth/v2/token
```

**Workaround:**
- Generate token manually via Uber Developer Dashboard OAuth Playground
- Use that token for API calls
- Refresh manually when it expires (~30 days)

**Long-term Fix:**
- Contact Uber support
- Ask about client credentials flow for production apps
- Verify correct OAuth endpoint and parameters

---

## 📝 API Credentials

### Your App Details
```
Client ID: ypYKCyBCZRYqzkJRfUmE7vBPGxrru5yk
Client Secret: i7ET6du4qb_paToesQ9Ue9ruEnfsZyvUVf1jjjrY
Scopes: eats.report, eats.store
App Name: Barrys_Reporting
```

### Example Store
```
Store UUID: ad2e72b9-e94d-5cb3-9675-51b7854711f3
Store Name: Barry's Bootcamp (example)
```

### Webhook Configuration
```
Primary Webhook URL: https://uber-eats-webhook-verifier-4eadylqnda-ue.a.run.app/uber-webhook
Event Type: eats.report.success
Signature Header: X-Uber-Signature
Signature Algorithm: HMAC-SHA256 (lowercase hex)
```

---

## 🎯 Summary

**What We're Using:**
1. **Stores API** → Get store list → `UBER_EATS_STORES`
2. **Reports API** → Trigger report → Get `workflow_uuid`
3. **Webhooks** → Receive notification → Get `download_url`
4. **CSV Download** → Download report → Parse and store → `UBER_EATS_REPORT_DATA`

**What We're Getting:**
- Store information (names, locations, timezones)
- Financial reports (sales, fees, payouts)
- 35 columns of detailed financial metrics per store
- Daily/weekly data for analytics

**Current Status:**
- ✅ Webhook receiver working
- ✅ CSV download working
- ✅ Snowflake storage working
- ❌ Automated report triggering (OAuth issue)
