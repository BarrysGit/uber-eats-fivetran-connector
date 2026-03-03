# How the Uber Eats Fivetran Connector Works

## Overview

This connector receives real-time webhook notifications from Uber Eats when reports are ready, automatically downloads the report data, and stores it in Snowflake using a Fivetran-compatible schema. It eliminates manual CSV downloads and provides near real-time data sync.

## Architecture

```
┌─────────────┐         ┌──────────────────────┐         ┌─────────────┐
│  Uber Eats  │ webhook │  Cloud Run Service   │  store  │  Snowflake  │
│  Platform   ├────────>│  (webhook-verifier)  ├────────>│  Database   │
└─────────────┘         └──────────────────────┘         └─────────────┘
                                 │
                                 │ download
                                 v
                        ┌──────────────────┐
                        │  Uber CSV API    │
                        │  (Report Data)   │
                        └──────────────────┘
```

## How It Works: Step-by-Step

### 1. **Webhook Registration** (One-Time Setup)

- You register a webhook URL with Uber Eats Developer Dashboard
- Webhook URL: `https://your-cloud-run-service.run.app/uber-webhook`
- Uber requires you to provide a `client_secret` during webhook setup
- This secret is used to sign all webhook requests with HMAC-SHA256

### 2. **Report Generation Trigger**

When a report is ready (e.g., daily sales report), Uber Eats:
- Generates a CSV file with the report data
- Creates a time-limited download URL for the CSV
- Sends a webhook POST request to your registered URL

**Example Webhook Payload:**
```json
{
  "event_id": "evt_abc123",
  "job_id": "job_xyz789",
  "event_type": "eats.report.success",
  "report_type": "EATS_STORE_DAILY_SALES_SUMMARY_REPORT_V2",
  "start_time_ms": 1704067200000,
  "end_time_ms": 1704153599000,
  "report_metadata": {
    "sections": [
      {
        "download_url": "https://uber-reports.s3.amazonaws.com/...",
        "section_type": "STORE"
      }
    ],
    "store_uuids": ["store-uuid-1", "store-uuid-2"]
  }
}
```

### 3. **Webhook Receipt & Signature Verification**

Our Cloud Run service receives the webhook and:

**a) Reads Raw Request Body**
```python
raw_body = await request.body()  # Must read raw bytes, not parsed JSON
```

**b) Extracts Signature Header**
```python
x_uber_signature = Header("X-Uber-Signature")  # HMAC-SHA256 signature
```

**c) Verifies Authenticity**
```python
computed_signature = hmac.new(
    client_secret.encode('utf-8'),
    raw_body,
    hashlib.sha256
).hexdigest()

# Constant-time comparison prevents timing attacks
is_valid = hmac.compare_digest(computed_signature, x_uber_signature)
```

**Why Raw Body?**
- Signature is computed over the exact bytes Uber sent
- Parsing JSON first can change formatting (spaces, order) and break verification
- Even one byte difference = signature mismatch

### 4. **CSV Download**

Once verified, the service:

**a) Extracts Download URL**
```python
download_url = payload["report_metadata"]["sections"][0]["download_url"]
```

**b) Downloads CSV File**
```python
response = requests.get(download_url, timeout=60)
csv_content = response.content.decode('utf-8-sig')  # Strip BOM if present
```

**c) Parses CSV Data**
```python
csv_reader = csv.DictReader(io.StringIO(csv_content))
rows = list(csv_reader)
# Example row: {"Store ID": "...", "Sales": "123.45", "Orders": "10"}
```

**Key Features:**
- Automatic retry on network failures (3 attempts)
- BOM (Byte Order Mark) removal for Unicode CSVs
- Column name cleaning (strips whitespace)
- Timeout protection (60 seconds)

### 5. **Snowflake Storage**

The service stores data in two Fivetran-compatible tables:

#### Table 1: `UBER_EATS_REPORTS` (Report Metadata)

Stores webhook metadata for each report:

```sql
CREATE TABLE UBER_EATS_REPORTS (
    WORKFLOW_ID VARCHAR PRIMARY KEY,        -- event_id from webhook
    REPORT_TYPE VARCHAR,                     -- e.g., "EATS_STORE_DAILY_SALES_SUMMARY"
    STATUS VARCHAR,                          -- "COMPLETED"
    START_DATE DATE,                         -- Report start date
    END_DATE DATE,                           -- Report end date
    STORE_UUIDS VARIANT,                     -- JSON array of store IDs
    DOWNLOAD_URL VARCHAR,                    -- CSV download URL
    CREATED_AT_UTC TIMESTAMP,                -- When webhook was received
    DOWNLOADED_AT_UTC TIMESTAMP,             -- When CSV was downloaded
    _FIVETRAN_SYNCED TIMESTAMP,              -- Fivetran compatibility
    _FIVETRAN_DELETED BOOLEAN                -- Soft delete flag
);
```

**Insert Logic (MERGE for Idempotency):**
```python
# Uses MERGE so duplicate webhooks don't create duplicate rows
MERGE INTO UBER_EATS_REPORTS AS target
USING (SELECT event_id, ...) AS source
ON target.WORKFLOW_ID = source.WORKFLOW_ID
WHEN MATCHED THEN UPDATE ...
WHEN NOT MATCHED THEN INSERT ...
```

#### Table 2: `UBER_EATS_REPORT_DATA` (CSV Data)

Stores the actual CSV rows as JSON:

```sql
CREATE TABLE UBER_EATS_REPORT_DATA (
    ID NUMBER AUTOINCREMENT PRIMARY KEY,
    WORKFLOW_ID VARCHAR,                     -- Links to UBER_EATS_REPORTS
    REPORT_DATA VARCHAR,                     -- JSON string of CSV row
    _FIVETRAN_SYNCED TIMESTAMP,
    _FIVETRAN_DELETED BOOLEAN
);
```

**Example Row:**
```sql
WORKFLOW_ID: "evt_abc123"
REPORT_DATA: {"Store ID": "store-1", "Sales": "123.45", "Orders": "10"}
```

**Incremental Approach:**
```python
# Delete old data for this workflow_id first (deduplication)
DELETE FROM UBER_EATS_REPORT_DATA WHERE WORKFLOW_ID = %s

# Insert new CSV rows
INSERT INTO UBER_EATS_REPORT_DATA (WORKFLOW_ID, REPORT_DATA, ...)
VALUES (%s, json.dumps(row), ...)
```

### 6. **Response to Uber**

After successful storage:

```python
# Uber requires: "HTTP 200 with empty response body"
return PlainTextResponse(content="", status_code=200)
```

**Why Empty Body?**
- Uber's webhook spec requires empty 200 response
- Any content in body may cause Uber to treat it as error
- Non-200 status = Uber will retry webhook

**Error Handling:**
- `401 Unauthorized` - Invalid signature (Uber won't retry)
- `502 Bad Gateway` - Storage failed (Uber will retry)
- `500 Internal Server Error` - Unexpected error (Uber will retry)

## Data Flow Timeline

```
0ms:  Uber sends webhook → Cloud Run
1ms:  Service receives request, extracts signature
2ms:  Verifies HMAC-SHA256 signature ✓
3ms:  Parses JSON payload
4ms:  Extracts download_url
100ms: Downloads CSV from Uber's S3 (network latency)
200ms: Parses 1000 CSV rows
250ms: Connects to Snowflake
300ms: Inserts metadata into UBER_EATS_REPORTS
500ms: Inserts 1000 rows into UBER_EATS_REPORT_DATA
550ms: Returns HTTP 200 to Uber ✓
```

**Total Latency:** ~550ms for 1000 rows

## Security Features

### 1. **HMAC Signature Verification**
- Every webhook includes `X-Uber-Signature` header
- Computed as: `HMAC-SHA256(client_secret, raw_request_body)`
- Prevents spoofed/malicious webhooks
- Uses constant-time comparison to prevent timing attacks

### 2. **TLS/HTTPS**
- All communication over HTTPS
- Cloud Run enforces TLS 1.2+
- Certificates managed by Google

### 3. **Secret Management**
- `UBER_CLIENT_SECRET` stored in Google Secret Manager
- `SNOWFLAKE_PASSWORD` stored in Google Secret Manager
- Never logged or exposed in code
- Rotatable without code changes

### 4. **Private Key Authentication (Optional)**
- Supports Snowflake private key authentication
- More secure than password auth
- Key stored in Secret Manager, parsed at runtime

## Error Handling & Retries

### Webhook Verification Errors

| Error | Status Code | Uber Retries? | Reason |
|-------|-------------|---------------|--------|
| Missing signature | 401 | No | Client error |
| Invalid signature | 401 | No | Wrong secret |
| Empty body | 400 | No | Malformed request |
| Invalid JSON | 400 | No | Parse error |

### Storage Errors

| Error | Status Code | Uber Retries? | Reason |
|-------|-------------|---------------|--------|
| Snowflake connection failed | 502 | Yes | Transient |
| CSV download failed | 502 | Yes | Network issue |
| Database insert failed | 502 | Yes | Recoverable |
| Unexpected error | 500 | Yes | Unknown |

**Retry Strategy:**
- Uber retries with exponential backoff
- Max retries: ~10 attempts over 24 hours
- Eventually gives up and logs failure

### Our Internal Retries

**CSV Download:**
- 3 attempts with 2s, 4s, 6s delays
- Only retries on 5xx errors or network failures
- 4xx errors (e.g., expired URL) fail immediately

**Snowflake Operations:**
- No automatic retries (handled by Uber's webhook retry)
- Connection pooling disabled (Cloud Run is stateless)
- Each webhook creates new connection

## Monitoring & Health Checks

### Health Endpoint

```bash
GET /health
```

**Response:**
```json
{
  "status": "ok",
  "snowflake": "connected"
}
```

**What It Checks:**
- Service is running
- Snowflake credentials valid
- Database connection works
- Can execute queries

**Used By:**
- Cloud Run health checks
- Uptime monitoring
- Load balancer routing

### Logging

All operations logged with timestamps:

```
2024-01-01 10:00:00 - INFO - Received POST /uber-webhook (incoming webhook)
2024-01-01 10:00:00 - INFO - ✅ Signature validated, storing in Snowflake
2024-01-01 10:00:01 - INFO - Downloading CSV from URL (attempt 1/3): https://...
2024-01-01 10:00:02 - INFO - ✅ Downloaded and parsed CSV: 1000 rows
2024-01-01 10:00:03 - INFO - ✅ MERGE into UBER_EATS_REPORTS: workflow_id=evt_abc123
2024-01-01 10:00:04 - INFO - ✅ Stored 1000 rows in UBER_EATS_REPORT_DATA for workflow_id=evt_abc123
2024-01-01 10:00:04 - INFO - ✅ Successfully stored webhook in Snowflake
```

**View Logs:**
```bash
gcloud logging read "resource.type=cloud_run_revision" --limit 50
```

## Deployment Architecture

### Google Cloud Run

**Why Cloud Run?**
- Serverless - scales to zero when idle
- Auto-scales to handle traffic spikes
- Pay per request (not per hour)
- Built-in HTTPS & load balancing
- Integrates with Secret Manager

**Configuration:**
```yaml
Service: uber-eats-webhook-verifier
Region: us-central1
Memory: 512 MiB
CPU: 1
Timeout: 300s (5 minutes)
Max Instances: 10
Min Instances: 0 (scales to zero)
```

**Environment Variables:**
```bash
SNOWFLAKE_USER=GITHUB_ACTIONS
SNOWFLAKE_ACCOUNT=abc12345.us-east-1
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=UBER_EATS_CLOUDRUN
SNOWFLAKE_SCHEMA=UBER_EATS
```

**Secrets (from Secret Manager):**
```bash
UBER_CLIENT_SECRET → projects/.../secrets/uber-client-secret/versions/latest
SNOWFLAKE_PASSWORD → projects/.../secrets/snowflake-password/versions/latest
```

### Container Image

**Dockerfile:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/main_snowflake.py main.py
CMD ["python", "main.py"]
```

**Build & Deploy:**
```bash
gcloud run deploy uber-eats-webhook-verifier \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars SNOWFLAKE_DATABASE=UBER_EATS_CLOUDRUN \
  --set-secrets UBER_CLIENT_SECRET=uber-client-secret:latest
```

## Fivetran Schema Compatibility

This connector produces the exact same schema as Fivetran's Uber Eats connector:

### Schema Comparison

| Feature | Fivetran | This Connector | Match? |
|---------|----------|----------------|--------|
| Table: `UBER_EATS_REPORTS` | ✓ | ✓ | ✅ |
| Table: `UBER_EATS_REPORT_DATA` | ✓ | ✓ | ✅ |
| Column: `WORKFLOW_ID` (PK) | ✓ | ✓ | ✅ |
| Column: `REPORT_TYPE` | ✓ | ✓ | ✅ |
| Column: `START_DATE` / `END_DATE` | ✓ | ✓ | ✅ |
| Column: `DOWNLOAD_URL` | ✓ | ✓ | ✅ |
| Column: `_FIVETRAN_SYNCED` | ✓ | ✓ | ✅ |
| JSON data in `REPORT_DATA` | ✓ | ✓ | ✅ |

**Benefits:**
- Drop-in replacement for Fivetran
- Existing queries work without changes
- Same dbt models can be reused
- BI dashboards compatible

## Performance Characteristics

### Latency

| Operation | Time | Notes |
|-----------|------|-------|
| Signature verification | <1ms | In-memory HMAC |
| CSV download | 50-500ms | Network dependent |
| CSV parsing | 10-50ms | 1000 rows |
| Snowflake connection | 100-300ms | Cold start |
| Insert 1000 rows | 200-500ms | Batch insert |
| **Total webhook processing** | **400-1500ms** | End-to-end |

### Throughput

- **Max concurrent webhooks:** 10 (Cloud Run max instances)
- **Requests per second:** ~10-20 RPS (limited by Snowflake connection time)
- **Daily capacity:** ~864,000 webhooks (unrealistic for Uber Eats)

**Typical Usage:**
- Uber Eats sends ~10-100 webhooks per day per store
- Most stores: 1-10 locations
- Expected load: 10-1000 webhooks/day

### Cost Estimate

**Google Cloud Run:**
- CPU: $0.00002400 per vCPU-second
- Memory: $0.00000250 per GiB-second
- Requests: $0.40 per million requests

**Example:**
- 100 webhooks/day
- 1 second per webhook
- 512 MiB memory

```
Monthly cost:
= (100 webhooks × 30 days) × ($0.000024 + $0.00000125)
= 3000 × $0.00002525
= $0.08/month

+ 3000 requests × ($0.40 / 1M)
= $0.0012/month

Total: ~$0.08/month
```

**Snowflake Costs:**
- Separate from Cloud Run
- Depends on warehouse size and query time
- Typical: $2-$10/month for light usage

## Querying the Data

### Get All Reports

```sql
SELECT 
    WORKFLOW_ID,
    REPORT_TYPE,
    START_DATE,
    END_DATE,
    DOWNLOADED_AT_UTC,
    ARRAY_SIZE(STORE_UUIDS) AS num_stores
FROM UBER_EATS.UBER_EATS_REPORTS
ORDER BY CREATED_AT_UTC DESC;
```

### Get Report Data (Parsed JSON)

```sql
SELECT 
    r.WORKFLOW_ID,
    r.REPORT_TYPE,
    r.START_DATE,
    PARSE_JSON(d.REPORT_DATA) AS data
FROM UBER_EATS.UBER_EATS_REPORTS r
JOIN UBER_EATS.UBER_EATS_REPORT_DATA d
    ON r.WORKFLOW_ID = d.WORKFLOW_ID
WHERE r.REPORT_TYPE = 'EATS_STORE_DAILY_SALES_SUMMARY_REPORT_V2'
ORDER BY r.START_DATE DESC;
```

### Extract Specific Fields from JSON

```sql
SELECT 
    WORKFLOW_ID,
    PARSE_JSON(REPORT_DATA)::"Store ID"::VARCHAR AS store_id,
    PARSE_JSON(REPORT_DATA)::"Net Sales"::FLOAT AS net_sales,
    PARSE_JSON(REPORT_DATA)::"Total Orders"::INT AS total_orders
FROM UBER_EATS.UBER_EATS_REPORT_DATA
WHERE WORKFLOW_ID = 'evt_abc123';
```

### Daily Sales Summary

```sql
SELECT 
    r.START_DATE,
    SUM(PARSE_JSON(d.REPORT_DATA)::"Net Sales"::FLOAT) AS total_sales,
    SUM(PARSE_JSON(d.REPORT_DATA)::"Total Orders"::INT) AS total_orders
FROM UBER_EATS.UBER_EATS_REPORTS r
JOIN UBER_EATS.UBER_EATS_REPORT_DATA d
    ON r.WORKFLOW_ID = d.WORKFLOW_ID
WHERE r.REPORT_TYPE = 'EATS_STORE_DAILY_SALES_SUMMARY_REPORT_V2'
GROUP BY r.START_DATE
ORDER BY r.START_DATE DESC;
```

## Troubleshooting

### Webhook Not Received

**Check:**
1. Webhook URL registered correctly in Uber Developer Dashboard
2. Cloud Run service is running: `gcloud run services list`
3. Service allows unauthenticated requests: `--allow-unauthenticated`
4. No firewall blocking inbound traffic

**Test:**
```bash
curl -X POST https://your-service.run.app/uber-webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

### Signature Verification Failing

**Check:**
1. `UBER_CLIENT_SECRET` matches Uber Developer Dashboard
2. Secret Manager version is `latest`
3. Raw body not modified before verification

**Debug:**
```python
logger.info(f"Received signature: {x_uber_signature}")
logger.info(f"Computed signature: {computed_signature}")
logger.info(f"Body length: {len(raw_body)} bytes")
```

### CSV Download Failing

**Check:**
1. Download URL not expired (usually 1 hour TTL)
2. Network connectivity from Cloud Run to S3
3. Firewall/proxy not blocking S3 requests

**Debug:**
```python
logger.info(f"Download URL: {download_url}")
response = requests.get(download_url, timeout=60)
logger.info(f"Response status: {response.status_code}")
logger.info(f"Response size: {len(response.content)} bytes")
```

### Snowflake Connection Failing

**Check:**
1. Credentials in Secret Manager are correct
2. Snowflake account/warehouse/database exist
3. Network connectivity from Cloud Run to Snowflake
4. IP whitelist includes Cloud Run egress IPs (if configured)

**Debug:**
```python
logger.info(f"Connecting to: {SNOWFLAKE_ACCOUNT}/{SNOWFLAKE_DATABASE}")
try:
    conn = get_snowflake_connection()
    logger.info("✅ Connected successfully")
except Exception as e:
    logger.error(f"❌ Connection failed: {str(e)}")
```

## Summary

This Uber Eats connector provides:

1. **Real-time sync** - Webhooks trigger immediate data ingestion
2. **Automatic CSV download** - No manual downloads needed
3. **Fivetran-compatible schema** - Drop-in replacement
4. **Secure** - HMAC verification, Secret Manager, TLS
5. **Scalable** - Cloud Run auto-scales to handle load
6. **Cost-effective** - Pay per webhook, scales to zero
7. **Reliable** - Automatic retries, health checks, logging

The connector bridges the gap between Uber Eats webhooks and Snowflake, providing a production-ready data pipeline without Fivetran's recurring costs.
