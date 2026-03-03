# Deploy Uber Eats Webhook Verifier

This webhook verifier receives webhooks from Uber Eats, verifies the HMAC signature, and forwards them to Fivetran.

## Architecture

```
Uber Eats → Webhook Verifier (validates HMAC) → Fivetran Webhooks → Snowflake → Custom Connector
```

## Prerequisites

1. **Google Cloud Project** with billing enabled
2. **gcloud CLI** installed and authenticated
3. **Fivetran Webhook URL** (from your Fivetran Webhooks connector)
4. **Uber Client Secret** (from Uber Developer Dashboard)

## Configuration

### Environment Variables

- `FIVETRAN_URL`: Your Fivetran webhook URL
  - **Current URL**: `https://webhooks.fivetran.com/webhooks/048f00c3-4aec-4b16-a7d3-f6db92b5f316`
- `UBER_CLIENT_SECRET`: Your Uber client secret
  - Get this from: Uber Developer Dashboard → Your App → Credentials

## Deployment Options

### Option 1: Google Cloud Run (Recommended)

#### Step 1: Build and Deploy

```bash
cd webhook-verifier-python

# Set your project ID
export PROJECT_ID=your-gcp-project-id
gcloud config set project $PROJECT_ID

# Build the container
gcloud builds submit --tag gcr.io/$PROJECT_ID/uber-eats-webhook-verifier

# Deploy to Cloud Run
gcloud run deploy uber-eats-webhook-verifier \
  --image gcr.io/$PROJECT_ID/uber-eats-webhook-verifier \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars FIVETRAN_URL=https://webhooks.fivetran.com/webhooks/048f00c3-4aec-4b16-a7d3-f6db92b5f316 \
  --set-secrets UBER_CLIENT_SECRET=uber-client-secret:latest \
  --set-secrets UBER_CLIENT_SECRET=uber-client-secret:latest \
  --memory 512Mi \
  --timeout 60s \
  --max-instances 10 \
  --min-instances 0
```

#### Step 2: Create Secret (if not already created)

```bash
# Create secret in Secret Manager
echo -n "your-uber-client-secret" | gcloud secrets create uber-client-secret \
  --data-file=- \
  --replication-policy="automatic"

# Grant Cloud Run access to the secret
gcloud secrets add-iam-policy-binding uber-client-secret \
  --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

#### Step 3: Get Your Webhook URL

After deployment, you'll get a URL like:
```
https://uber-eats-webhook-verifier-xxx-uc.a.run.app/uber-webhook
```

**Save this URL** - you'll use it in Uber Developer Console.

### Option 2: Local Testing

```bash
cd webhook-verifier-python

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export FIVETRAN_URL=https://webhooks.fivetran.com/webhooks/048f00c3-4aec-4b16-a7d3-f6db92b5f316
export UBER_CLIENT_SECRET=your-uber-client-secret  # Get from Uber Developer Dashboard

# Run locally
python main.py
```

The server will start on `http://localhost:8080`

Test with:
```bash
curl http://localhost:8080/health
```

### Option 3: Docker (Local or Other Cloud)

```bash
cd webhook-verifier-python

# Build image
docker build -t uber-eats-webhook-verifier .

# Run container
docker run -p 8080:8080 \
  -e FIVETRAN_URL=https://webhooks.fivetran.com/webhooks/048f00c3-4aec-4b16-a7d3-f6db92b5f316 \
  -e UBER_CLIENT_SECRET=your-uber-client-secret \
  uber-eats-webhook-verifier
```

## Configure Uber Developer Console

1. Go to [Uber Developer Dashboard](https://developer.uber.com/)
2. Select your app
3. Go to **Webhooks** section
4. Set **Primary Webhook URL** to your verifier endpoint:
   ```
   https://uber-eats-webhook-verifier-xxx-uc.a.run.app/uber-webhook
   ```
5. Enable webhook events:
   - `eats.report.success`
6. Save changes

## Testing

### Test with curl (using test script)

Use the test script in the parent directory:

```bash
cd ../..
python test_webhook.py
```

Or manually test:

```bash
# Generate a test signature
python3 -c "
import hmac, hashlib, json
secret = 'your-uber-client-secret'
body = json.dumps({'event_type': 'eats.report.success', 'workflow_id': 'test123'})
sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest().lower()
print(f'Signature: {sig}')
print(f'Body: {body}')
"

# Send test webhook
curl -X POST https://your-verifier-url/uber-webhook \
  -H "Content-Type: application/json" \
  -H "X-Uber-Signature: YOUR_SIGNATURE" \
  -d '{"event_type": "eats.report.success", "workflow_id": "test123"}'
```

## Monitoring

### Cloud Run Logs

```bash
# View logs
gcloud run services logs read uber-eats-webhook-verifier --region us-central1

# Stream logs
gcloud run services logs tail uber-eats-webhook-verifier --region us-central1
```

### Check Health

```bash
curl https://your-verifier-url/health
```

## Troubleshooting

### Signature Validation Failing

- ✅ Ensure `UBER_CLIENT_SECRET` is correct (from Uber Developer Dashboard)
- ✅ Ensure raw body is used (not parsed JSON) - FastAPI handles this correctly
- ✅ Check signature header is `X-Uber-Signature` (case-sensitive)

### Fivetran Not Receiving Webhooks

- ✅ Check verifier logs for forwarding errors
- ✅ Verify Fivetran webhook URL is correct
- ✅ Check Fivetran webhook connector is enabled
- ✅ Verify network connectivity from Cloud Run to Fivetran

### Webhook Not Received from Uber

- ✅ Check verifier endpoint is publicly accessible
- ✅ Check Uber Developer Console webhook URL is correct
- ✅ Verify Uber app has `eats.report` scope
- ✅ Check verifier logs for incoming requests

## Security Best Practices

1. **Use Secrets Manager**: Store `UBER_CLIENT_SECRET` in Google Secret Manager
2. **HTTPS Only**: Always use HTTPS (Cloud Run provides this automatically)
3. **Monitor Logs**: Set up alerts for failed signature validations
4. **Rate Limiting**: Consider adding rate limiting (Cloud Run has built-in limits)
5. **IP Allowlisting**: Optionally restrict to Uber's IP ranges (if known)

## Cost Estimation (Cloud Run)

- **Free Tier**: 2 million requests/month
- **Pricing**: $0.40 per million requests after free tier
- **Memory**: 512Mi is sufficient for most workloads
- **Estimated Cost**: < $1/month for typical usage

## Next Steps

1. ✅ Deploy the verifier
2. ✅ Configure Uber Developer Console with verifier URL
3. ✅ Test with a sample webhook
4. ✅ Monitor logs to verify webhooks are being forwarded
5. ✅ Check Fivetran webhook connector for received events
6. ✅ Verify data appears in Snowflake `webhooks.uber_eats_webhooks` table

