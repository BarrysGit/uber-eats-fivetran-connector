# Uber Eats Webhook Verifier (Python)

A FastAPI-based webhook verifier that receives webhooks from Uber Eats, verifies HMAC signatures, and forwards them to Fivetran.

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
2. **Reads raw body bytes** (critical for signature verification)
3. **Verifies HMAC SHA-256 signature** using `X-Uber-Signature` header
4. **Forwards to Fivetran** if signature is valid
5. **Returns 502** if forwarding fails (so Uber will retry)

## Key Features

- ✅ **HMAC Signature Verification**: Uses constant-time comparison to prevent timing attacks
- ✅ **Raw Body Handling**: Preserves exact bytes for signature verification
- ✅ **Error Handling**: Proper HTTP status codes for different error scenarios
- ✅ **Logging**: Comprehensive logging for debugging
- ✅ **Health Check**: `/health` endpoint for monitoring

## Architecture

```
Uber Eats → Webhook Verifier (validates HMAC) → Fivetran Webhooks → Snowflake → Custom Connector
```

## Deployment

See [DEPLOY.md](./DEPLOY.md) for detailed deployment instructions for:
- Google Cloud Run (recommended)
- Docker
- Local testing

## Configuration

Required environment variables:

- `FIVETRAN_URL`: Your Fivetran webhook URL
- `UBER_CLIENT_SECRET`: Your Uber client secret (from Uber Developer Dashboard)
- `PORT`: Server port (default: 8080)

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

## Troubleshooting

See [DEPLOY.md](./DEPLOY.md) for troubleshooting guide.

