# OAuth Integration - Code Changes Summary

## What Was Added

Added Uber OAuth 2.0 authorization code flow to support integration activation, while preserving all existing webhook and Snowflake functionality.

## Code Changes

### 1. New Imports

```python
from fastapi import FastAPI, Request, Header, HTTPException, status, Query
from fastapi.responses import PlainTextResponse, RedirectResponse, JSONResponse
```

**Added:**
- `Query` - for query parameter parsing
- `RedirectResponse` - for OAuth redirects
- `JSONResponse` - for structured JSON responses

### 2. New Environment Variables

```python
# OAuth Configuration (optional - only needed for OAuth flow)
UBER_CLIENT_ID = os.getenv("UBER_CLIENT_ID", "").strip()
UBER_REDIRECT_URI = os.getenv("UBER_REDIRECT_URI", "").strip()
```

**Note:** These are optional. The service still works without them (webhooks only).

### 3. New Helper Function

```python
def exchange_authorization_code_for_token(code: str) -> Dict[str, Any]:
    """
    Exchange Uber authorization code for access token.
    
    - Validates required OAuth env vars
    - POSTs to https://auth.uber.com/oauth/v2/token
    - Returns parsed token response
    - Logs scope and expires_in (NOT the token itself)
    - Raises HTTPException on failure
    """
```

**Location:** Added after `store_report_data()` function (line ~451)

### 4. New Endpoint: GET `/uber/authorize`

```python
@app.get("/uber/authorize")
async def uber_authorize():
    """
    OAuth Step 1: Redirect to Uber authorization page
    """
```

**What it does:**
1. Checks `UBER_CLIENT_ID` and `UBER_REDIRECT_URI` are set
2. Builds authorization URL: `https://auth.uber.com/oauth/v2/authorize`
3. Redirects user to Uber (HTTP 307)
4. Uber shows permission grant screen

**Example redirect:**
```
https://auth.uber.com/oauth/v2/authorize?client_id=ABC&response_type=code&redirect_uri=https://...&scope=eats.pos_provisioning
```

### 5. New Endpoint: GET `/uber/callback`

```python
@app.get("/uber/callback")
async def uber_callback(code: Optional[str] = Query(None)):
    """
    OAuth Step 2: Receive auth code and exchange for token
    """
```

**What it does:**
1. Receives `code` query parameter from Uber
2. Validates code is present (400 if missing)
3. Calls `exchange_authorization_code_for_token(code)`
4. Returns safe JSON response (NO access token in response)

**Success response:**
```json
{
  "status": "success",
  "message": "Authorization successful",
  "scope": "eats.pos_provisioning",
  "expires_in": 2592000
}
```

## All Endpoints (After Changes)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/uber-webhook` | GET/HEAD | Allow verification |
| `/uber-webhook` | POST | Receive webhooks |
| `/uber/authorize` | GET | **NEW:** Start OAuth |
| `/uber/callback` | GET | **NEW:** Complete OAuth |

## Environment Variables Required

### For Webhooks (Existing - No Changes)

```bash
# Required
UBER_CLIENT_SECRET=your_uber_client_secret
SNOWFLAKE_USER=GITHUB_ACTIONS
SNOWFLAKE_ACCOUNT=abc12345.us-east-1
SNOWFLAKE_WAREHOUSE=COMPUTE_WH

# One of these required
SNOWFLAKE_PASSWORD=your_password
# OR
SNOWFLAKE_PRIVATE_KEY=your_private_key

# Optional
SNOWFLAKE_DATABASE=UBER_EATS_CLOUDRUN
SNOWFLAKE_SCHEMA=UBER_EATS
PORT=8080
```

### For OAuth (New - Optional)

```bash
# Only needed if using OAuth endpoints
UBER_CLIENT_ID=your_uber_client_id
UBER_REDIRECT_URI=https://your-service.run.app/uber/callback
```

**Important:** If you don't set these OAuth variables:
- Webhook endpoints still work fine
- OAuth endpoints return error: `oauth_configuration_missing`

## Deployment Steps

### Option 1: Deploy Without OAuth (Webhooks Only)

```bash
# Current deployment works as-is
gcloud run deploy uber-eats-webhook-verifier \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars SNOWFLAKE_DATABASE=UBER_EATS_CLOUDRUN,SNOWFLAKE_SCHEMA=UBER_EATS \
  --set-secrets UBER_CLIENT_SECRET=uber-client-secret:latest,SNOWFLAKE_PASSWORD=snowflake-password:latest
```

### Option 2: Deploy With OAuth Support

```bash
# Get your Cloud Run service URL first
SERVICE_URL=$(gcloud run services describe uber-eats-webhook-verifier --region us-central1 --format="value(status.url)")

# Deploy with OAuth env vars
gcloud run deploy uber-eats-webhook-verifier \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars SNOWFLAKE_DATABASE=UBER_EATS_CLOUDRUN,SNOWFLAKE_SCHEMA=UBER_EATS,UBER_CLIENT_ID=your_client_id,UBER_REDIRECT_URI=${SERVICE_URL}/uber/callback \
  --set-secrets UBER_CLIENT_SECRET=uber-client-secret:latest,SNOWFLAKE_PASSWORD=snowflake-password:latest
```

**Replace `your_client_id`** with your actual Uber Client ID.

### Option 3: Add OAuth to Existing Deployment

```bash
# Update only environment variables (faster)
gcloud run services update uber-eats-webhook-verifier \
  --region us-central1 \
  --set-env-vars UBER_CLIENT_ID=your_client_id,UBER_REDIRECT_URI=https://uber-eats-webhook-verifier-xyz-uc.a.run.app/uber/callback
```

## Uber Developer Dashboard Setup

After deployment, configure in Uber Developer Dashboard:

### 1. Get Your Cloud Run URL

```bash
gcloud run services describe uber-eats-webhook-verifier \
  --region us-central1 \
  --format="value(status.url)"
```

**Example output:** `https://uber-eats-webhook-verifier-abc123-uc.a.run.app`

### 2. Add to Uber Dashboard

**Section:** OAuth Settings → Redirect URIs

**Add this URL:**
```
https://uber-eats-webhook-verifier-abc123-uc.a.run.app/uber/callback
```

**Important:** Must be exact match (no trailing slash, correct protocol)

### 3. Webhook URL (Unchanged)

**Section:** Webhooks

**Existing URL (no changes needed):**
```
https://uber-eats-webhook-verifier-abc123-uc.a.run.app/uber-webhook
```

## Testing the OAuth Flow

### Step 1: Test Authorization Redirect

Open in browser:
```
https://your-service.run.app/uber/authorize
```

**Expected:**
- Redirects to `auth.uber.com`
- Shows Uber login page
- After login, shows permission grant screen

### Step 2: Grant Permission

Click "Allow" on Uber's page

**Expected:**
- Redirects to your `/uber/callback`
- Shows success JSON response
- Check logs for "Token exchange successful"

### Step 3: Verify Logs

```bash
gcloud logging read "resource.type=cloud_run_revision" --limit 20
```

**Look for:**
```
Redirecting to Uber authorization (scope: eats.pos_provisioning)
OAuth callback received with authorization code
Exchanging authorization code for access token
✅ Token exchange successful - scope: eats.pos_provisioning, expires_in: 2592000s
```

### Step 4: Verify Webhooks Still Work

```bash
# Should still return 200
curl -X POST https://your-service.run.app/uber-webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

## What's NOT Implemented Yet

This OAuth implementation is minimal. It does NOT:

- ❌ Store access token in database
- ❌ Use token for API calls
- ❌ Implement token refresh
- ❌ Persist OAuth state across restarts
- ❌ Handle token expiration

**Current behavior:** Token is returned and discarded. You'll need to add persistence if you want to use the token for API calls.

## Next Steps (Optional)

If you need to use the OAuth token:

1. **Create token storage table:**
```sql
CREATE TABLE UBER_OAUTH_TOKENS (
    ID NUMBER AUTOINCREMENT PRIMARY KEY,
    ACCESS_TOKEN VARCHAR,
    REFRESH_TOKEN VARCHAR,
    SCOPE VARCHAR,
    EXPIRES_AT TIMESTAMP,
    CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);
```

2. **Modify `/uber/callback`:**
```python
# After token exchange
store_token_in_snowflake(token_data)
```

3. **Add token retrieval:**
```python
def get_valid_uber_token() -> str:
    # Get token from Snowflake
    # Check if expired
    # Refresh if needed
    # Return valid token
```

4. **Use for API calls:**
```python
headers = {"Authorization": f"Bearer {get_valid_uber_token()}"}
response = requests.get("https://api.uber.com/v1/eats/stores", headers=headers)
```

## Security Notes

### What's Logged (Safe)

```python
logger.info("Redirecting to Uber authorization")
logger.info("OAuth callback received with authorization code")
logger.info(f"Token exchange successful - scope: {scope}, expires_in: {expires_in}s")
```

### What's NOT Logged (Sensitive)

```python
# These are NEVER logged:
# - access_token
# - refresh_token
# - client_secret
# - full authorization code
```

### Error Responses

All error responses are safe for production:
- No sensitive data in response body
- No stack traces exposed
- Clear error codes for debugging

## Summary

**Changes made:**
- ✅ Added 2 new OAuth endpoints
- ✅ Added 1 helper function for token exchange
- ✅ Added 2 new optional environment variables
- ✅ Preserved all existing webhook functionality
- ✅ Added comprehensive error handling
- ✅ Added safe logging (no secrets)
- ✅ Production-ready code quality

**No breaking changes:**
- ✅ All existing endpoints unchanged
- ✅ Snowflake logic intact
- ✅ Webhook processing preserved
- ✅ Same deployment process (just add optional env vars)

The service is backward compatible. You can deploy immediately and add OAuth env vars later when needed.
