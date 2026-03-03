# Uber Eats Fivetran Connector

A production-ready webhook receiver for Uber Eats that automatically downloads reports and stores them in Snowflake using a Fivetran-compatible schema. Deployed on Google Cloud Run for automatic scaling and high availability.

## 📖 Documentation

**[→ How It Works - Complete Technical Guide](./HOW_IT_WORKS.md)**

Comprehensive documentation covering:
- Architecture and data flow
- Step-by-step webhook processing
- Security features (HMAC verification, TLS, secrets)
- Snowflake schema design (Fivetran-compatible)
- Performance characteristics and cost analysis
- Querying examples and troubleshooting

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export FIVETRAN_URL=https://webhooks.fivetran.com/webhooks/048f00c3-4aec-4b16-a7d3-f6db92b5f316
export UBER_CLIENT_SECRET=your-uber-client-secret  # Get from Uber Developer Dashboard

# Run server
python main.py
```

Server will start on `http://localhost:8080`

### Test Health Endpoint

```bash
curl http://localhost:8080/health
```

## How It Works

1. **Receives webhook** from Uber Eats at `/uber-webhook`
2. **Verifies HMAC SHA-256 signature** using `X-Uber-Signature` header
3. **Downloads CSV** from Uber's report URL automatically
4. **Stores in Snowflake** with Fivetran-compatible schema
5. **Returns 200** to acknowledge receipt (or 502 for retry)

**For detailed technical explanation, see [HOW_IT_WORKS.md](./HOW_IT_WORKS.md)**

## Key Features

- ✅ **Real-time Webhook Processing**: Receives webhooks from Uber Eats automatically
- ✅ **HMAC Signature Verification**: Secure authentication using constant-time comparison
- ✅ **Automatic CSV Download**: Downloads and parses report CSVs from Uber's S3
- ✅ **Direct Snowflake Integration**: Stores data directly in Snowflake (no Fivetran needed)
- ✅ **Fivetran-Compatible Schema**: Drop-in replacement for existing Fivetran setups
- ✅ **Cloud Run Deployment**: Serverless, auto-scaling, cost-effective
- ✅ **Comprehensive Logging**: Full visibility into webhook processing
- ✅ **Health Checks**: Built-in monitoring and health endpoints

## Architecture

```
Uber Eats → Cloud Run (validates HMAC + downloads CSV) → Snowflake Database
```

**Two Implementations Available:**

1. **`main_snowflake.py`** (Recommended): Direct Snowflake integration with automatic CSV download
2. **`main.py`** (Legacy): Forwards to Fivetran Webhooks connector

See [HOW_IT_WORKS.md](./HOW_IT_WORKS.md) for detailed architecture diagrams and data flow.

## Deployment

See [DEPLOY.md](./DEPLOY.md) for detailed deployment instructions for:
- Google Cloud Run (recommended)
- Docker
- Local testing

## Configuration

### Required Environment Variables

**For Direct Snowflake Integration** (`main_snowflake.py`):

```bash
# Uber Configuration
UBER_CLIENT_SECRET=your-uber-client-secret

# Snowflake Configuration
SNOWFLAKE_USER=GITHUB_ACTIONS
SNOWFLAKE_PASSWORD=your-password  # Or use SNOWFLAKE_PRIVATE_KEY
SNOWFLAKE_ACCOUNT=abc12345.us-east-1
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=UBER_EATS_CLOUDRUN
SNOWFLAKE_SCHEMA=UBER_EATS

# Optional
PORT=8080  # Default: 8080
```

**For Fivetran Integration** (`main.py`):

```bash
UBER_CLIENT_SECRET=your-uber-client-secret
FIVETRAN_URL=https://webhooks.fivetran.com/webhooks/your-webhook-id
PORT=8080
```

## Security

- ✅ HMAC signature verification prevents unauthorized requests
- ✅ Constant-time comparison prevents timing attacks
- ✅ Raw body preservation ensures signature accuracy
- ✅ Proper error handling prevents information leakage

## Testing

Use the test script from the parent directory:

```bash
cd ../..
python test_webhook.py
```

Or test manually with curl (see DEPLOY.md for signature generation).

## Monitoring

Check logs for:
- `✅ Signature validated` - Webhook verified successfully
- `✅ Successfully forwarded to Fivetran` - Webhook forwarded successfully
- `Invalid signature` - Signature verification failed
- `Fivetran forwarding failed` - Error forwarding to Fivetran

## Database Schema

The connector creates two Fivetran-compatible tables:

### `UBER_EATS_REPORTS` (Report Metadata)
```sql
WORKFLOW_ID (PK) | REPORT_TYPE | STATUS | START_DATE | END_DATE | DOWNLOAD_URL | ...
```

### `UBER_EATS_REPORT_DATA` (CSV Data as JSON)
```sql
ID (PK) | WORKFLOW_ID (FK) | REPORT_DATA (JSON) | ...
```

See [HOW_IT_WORKS.md](./HOW_IT_WORKS.md) for complete schema details and query examples.

## Querying Data

```sql
-- Get all reports
SELECT * FROM UBER_EATS.UBER_EATS_REPORTS;

-- Get report data with parsed JSON
SELECT 
    r.START_DATE,
    PARSE_JSON(d.REPORT_DATA)::"Store ID"::VARCHAR AS store_id,
    PARSE_JSON(d.REPORT_DATA)::"Net Sales"::FLOAT AS net_sales
FROM UBER_EATS.UBER_EATS_REPORTS r
JOIN UBER_EATS.UBER_EATS_REPORT_DATA d
    ON r.WORKFLOW_ID = d.WORKFLOW_ID;
```

## Troubleshooting

Common issues and solutions:

- **Webhook not received**: Check Cloud Run service is running and URL is registered
- **Signature verification failing**: Verify `UBER_CLIENT_SECRET` matches Uber Dashboard
- **CSV download failing**: Check download URL hasn't expired (1 hour TTL)
- **Snowflake connection failing**: Verify credentials and network connectivity

See [HOW_IT_WORKS.md](./HOW_IT_WORKS.md#troubleshooting) for detailed troubleshooting guide.

