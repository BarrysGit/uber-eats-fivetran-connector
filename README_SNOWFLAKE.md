# Uber Eats Webhook Verifier (Direct to Snowflake)

This version **eliminates the Fivetran Webhooks connector** by writing directly to Snowflake.

## Architecture

```
Uber Eats → Webhook Verifier (validates HMAC + stores in Snowflake) → Snowflake → Custom Connector
```

**No Fivetran Webhooks connector needed!**

## What It Does

1. **Receives webhook** from Uber Eats at `/uber-webhook`
2. **Verifies HMAC signature** using `X-Uber-Signature` header
3. **Stores directly in Snowflake** table: `webhooks.uber_eats_webhooks`
4. **Custom connector** reads from Snowflake as before (no changes needed)

## Webhook Payload Structure

The webhook from Uber Eats contains **metadata about completed reports**, not the actual CSV data:

```json
{
  "event_type": "eats.report.success",
  "event_id": "abc123",
  "job_id": "job_456",
  "workflow_id": "2fc42be9-60fe-4752-999e-38ace2f7ca82",
  "report_type": "FINANCE_SUMMARY_REPORT",
  "report_metadata": {
    "sections": [
      {
        "content_type": "text/csv",
        "download_url": "https://tbgs-static.uber.com/report.csv?expires=..."
      }
    ]
  }
}
```

**Important**: The webhook contains the `download_url` - your custom connector downloads the actual CSV from this URL.

## Configuration

### Environment Variables

- `UBER_CLIENT_SECRET`: Your Uber client secret (from Uber Developer Dashboard)
- `SNOWFLAKE_ACCOUNT`: Snowflake account (e.g., `OLC69823.us-east-1`)
- `SNOWFLAKE_USER`: Snowflake username
- `SNOWFLAKE_PASSWORD`: Snowflake password
- `SNOWFLAKE_WAREHOUSE`: Snowflake warehouse
- `SNOWFLAKE_DATABASE`: Snowflake database
- `SNOWFLAKE_WEBHOOKS_SCHEMA`: Schema name (default: `webhooks`)
- `SNOWFLAKE_WEBHOOKS_TABLE`: Table name (default: `uber_eats_webhooks`)

## Snowflake Table Schema

The verifier creates/uses a table matching Fivetran's format:

```sql
CREATE TABLE IF NOT EXISTS webhooks.uber_eats_webhooks (
    event_id VARCHAR,
    job_id VARCHAR,
    event_type VARCHAR,
    body VARIANT,  -- JSON payload
    _fivetran_synced TIMESTAMP_NTZ
);
```

## Quick Start

### Local Testing

```bash
cd webhook-verifier-python

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export UBER_CLIENT_SECRET=your_signing_key_from_dashboard
export SNOWFLAKE_ACCOUNT=OLC69823.us-east-1
export SNOWFLAKE_USER=PC_FIVETRAN_USER
export SNOWFLAKE_PASSWORD=Barrysbootcamp123
export SNOWFLAKE_WAREHOUSE=PC_FIVETRAN_WH
export SNOWFLAKE_DATABASE=PC_FIVETRAN_DB
export SNOWFLAKE_WEBHOOKS_SCHEMA=webhooks
export SNOWFLAKE_WEBHOOKS_TABLE=uber_eats_webhooks

# Run server (using Snowflake version)
python main_snowflake.py
```

### Deploy to Google Cloud Run

```bash
cd webhook-verifier-python

export PROJECT_ID=your-gcp-project-id
gcloud config set project $PROJECT_ID

# Create secrets
echo -n "YOUR_SIGNING_KEY" | gcloud secrets create uber-client-secret --data-file=-
echo -n "Barrysbootcamp123" | gcloud secrets create snowflake-password --data-file=-

# Build and deploy
gcloud builds submit --tag gcr.io/$PROJECT_ID/uber-eats-webhook-verifier

gcloud run deploy uber-eats-webhook-verifier \
  --image gcr.io/$PROJECT_ID/uber-eats-webhook-verifier \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars \
    SNOWFLAKE_ACCOUNT=OLC69823.us-east-1,\
    SNOWFLAKE_USER=PC_FIVETRAN_USER,\
    SNOWFLAKE_WAREHOUSE=PC_FIVETRAN_WH,\
    SNOWFLAKE_DATABASE=PC_FIVETRAN_DB,\
    SNOWFLAKE_WEBHOOKS_SCHEMA=webhooks,\
    SNOWFLAKE_WEBHOOKS_TABLE=uber_eats_webhooks \
  --set-secrets \
    UBER_CLIENT_SECRET=uber-client-secret:latest,\
    SNOWFLAKE_PASSWORD=snowflake-password:latest \
  --memory 512Mi \
  --timeout 60s \
  --entrypoint "python main_snowflake.py"
```

## Update Dockerfile (if using Docker)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main_snowflake.py .

EXPOSE 8080

CMD ["python", "main_snowflake.py"]
```

## Benefits of This Approach

✅ **Eliminates Fivetran Webhooks connector** - One less component to manage  
✅ **Direct control** - You control the webhook storage logic  
✅ **Lower cost** - No Fivetran Webhooks connector fees  
✅ **Same interface** - Custom connector reads from Snowflake as before  
✅ **Faster** - Direct write to Snowflake (no intermediate step)

## Custom Connector Compatibility

Your custom connector (`connector.py`) already reads from `webhooks.uber_eats_webhooks` table. **No changes needed!** It will work exactly the same way.

The connector's `_query_snowflake_webhooks()` function will find webhooks stored by this verifier.

## Testing

1. **Test health endpoint**:
   ```bash
   curl https://your-verifier-url/health
   ```

2. **Test webhook** (use test script from parent directory):
   ```bash
   cd ../..
   python test_webhook.py
   ```

3. **Verify in Snowflake**:
   ```sql
   SELECT * FROM webhooks.uber_eats_webhooks 
   ORDER BY _fivetran_synced DESC 
   LIMIT 10;
   ```

## Monitoring

- Check Cloud Run logs for:
  - `✅ Signature validated`
  - `✅ Stored webhook in Snowflake`
  - `Error storing webhook in Snowflake` (if failures occur)

## Next Steps

1. ✅ Deploy the verifier (using `main_snowflake.py`)
2. ✅ Configure Uber Developer Console with verifier URL
3. ✅ Test with a sample webhook
4. ✅ Verify data appears in Snowflake
5. ✅ **Disable/delete the Fivetran Webhooks connector** (no longer needed!)
6. ✅ Custom connector will continue to work as before

