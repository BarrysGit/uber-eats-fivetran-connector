# Uber OAuth Setup Guide

This guide explains how to set up and use the OAuth 2.0 authorization flow for Uber Eats integration activation.

## Overview

The service now supports OAuth 2.0 authorization code flow, which allows Uber to grant access to your application for POS provisioning and other integration features.

## New Endpoints

### 1. GET `/uber/authorize`
**Purpose:** Initiates OAuth flow by redirecting user to Uber's authorization page

**Usage:**
```bash
# Navigate user to this URL in browser
https://your-service.run.app/uber/authorize
```

**What it does:**
- Validates OAuth configuration (client_id, redirect_uri)
- Redirects to: `https://auth.uber.com/oauth/v2/authorize`
- Requests scope: `eats.pos_provisioning`
- User logs in to Uber and grants permission

### 2. GET `/uber/callback`
**Purpose:** Receives authorization code from Uber and exchanges it for access token

**Uber redirects to:**
```
https://your-service.run.app/uber/callback?code=AUTHORIZATION_CODE
```

**Response (Success):**
```json
{
  "status": "success",
  "message": "Authorization successful",
  "scope": "eats.pos_provisioning",
  "expires_in": 2592000
}
```

**Response (Error):**
```json
{
  "error": "token_exchange_failed",
  "uber_status_code": 400,
  "uber_response": "invalid_grant"
}
```

## Required Environment Variables

Add these new environment variables to Cloud Run:

### New OAuth Variables

```bash
UBER_CLIENT_ID=your_uber_client_id
UBER_REDIRECT_URI=https://your-service.run.app/uber/callback
```

### Existing Variables (No Changes)

```bash
UBER_CLIENT_SECRET=your_uber_client_secret  # Already exists
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

## Cloud Run Deployment Update

When deploying with OAuth support, add the new environment variables:

```bash
gcloud run deploy uber-eats-webhook-verifier \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars SNOWFLAKE_DATABASE=UBER_EATS_CLOUDRUN,SNOWFLAKE_SCHEMA=UBER_EATS,UBER_CLIENT_ID=your_client_id,UBER_REDIRECT_URI=https://your-service.run.app/uber/callback \
  --set-secrets UBER_CLIENT_SECRET=uber-client-secret:latest,SNOWFLAKE_PASSWORD=snowflake-password:latest
```

**Important:** Replace `your_client_id` with your actual Uber client ID, and update the service URL in `UBER_REDIRECT_URI` after deployment.

## Uber Developer Dashboard Configuration

### 1. Add Redirect URI

In the Uber Developer Dashboard:

1. Go to your Uber Eats app
2. Navigate to **OAuth Settings** or **Redirect URIs**
3. Add: `https://your-service.run.app/uber/callback`
4. Save changes

**Example:**
```
Redirect URIs:
- https://uber-eats-webhook-verifier-abc123-uc.a.run.app/uber/callback
```

### 2. Verify Scopes

Ensure your app has access to:
- `eats.pos_provisioning` (for POS integration)

### 3. Get Client Credentials

You'll need:
- **Client ID** - Copy this to `UBER_CLIENT_ID` env var
- **Client Secret** - Already stored in Secret Manager as `UBER_CLIENT_SECRET`

## OAuth Flow (End-to-End)

### Step 1: User Initiates Authorization

User visits: `https://your-service.run.app/uber/authorize`

**What happens:**
1. Service validates OAuth configuration
2. Redirects to Uber authorization page
3. User sees: "Allow [Your App] to access your Uber Eats data?"

### Step 2: User Grants Permission

User clicks "Allow" on Uber's page

**What happens:**
1. Uber redirects to: `https://your-service.run.app/uber/callback?code=AUTH_CODE`
2. Service receives authorization code
3. Service exchanges code for access token (behind the scenes)
4. Service returns success response

### Step 3: Integration Activated

**Response:**
```json
{
  "status": "success",
  "message": "Authorization successful",
  "scope": "eats.pos_provisioning",
  "expires_in": 2592000
}
```

**Access token is valid for:**
- 2,592,000 seconds (30 days)
- Auto-refreshable (if refresh token is provided)

## Testing the OAuth Flow

### Test Authorization Redirect

```bash
curl -v https://your-service.run.app/uber/authorize
```

**Expected:** HTTP 307 redirect to `auth.uber.com`

### Test Callback (Simulated)

```bash
# You'll need a real authorization code from Uber
curl "https://your-service.run.app/uber/callback?code=REAL_AUTH_CODE"
```

**Expected:** JSON response with status, scope, expires_in

## Security Features

### 1. **No Token Logging**
- Access tokens are never logged
- Client secret is never logged
- Only scope and expires_in are logged

### 2. **Environment Variable Validation**
- Missing OAuth variables = clear error messages
- No silent failures or undefined behavior

### 3. **HTTPS Required**
- Cloud Run enforces TLS 1.2+
- Authorization codes encrypted in transit
- Redirect URI must use HTTPS

### 4. **Error Handling**
- Network failures handled gracefully
- Uber API errors returned with status codes
- No sensitive data leaked in error messages

## Troubleshooting

### Error: `oauth_configuration_missing`

**Problem:** Missing `UBER_CLIENT_ID` or `UBER_REDIRECT_URI`

**Fix:**
```bash
# Add to Cloud Run environment variables
gcloud run services update uber-eats-webhook-verifier \
  --region us-central1 \
  --set-env-vars UBER_CLIENT_ID=your_client_id,UBER_REDIRECT_URI=https://your-service.run.app/uber/callback
```

### Error: `token_exchange_failed`

**Common causes:**

1. **Invalid authorization code**
   - Code already used (can only use once)
   - Code expired (usually 10 minutes)
   - Code from different client_id

2. **Wrong redirect_uri**
   - Must exactly match Uber Developer Dashboard
   - Including protocol (https), port, path
   - No trailing slash

3. **Wrong client_secret**
   - Verify Secret Manager has correct value
   - Check secret version is `latest`

**Debug:**
```bash
# Check Cloud Run environment variables
gcloud run services describe uber-eats-webhook-verifier --region us-central1 --format="value(spec.template.spec.containers[0].env)"

# Check logs
gcloud logging read "resource.type=cloud_run_revision" --limit 50
```

### Error: `network_error`

**Problem:** Can't reach Uber token endpoint

**Check:**
1. Cloud Run has internet access (should by default)
2. Firewall not blocking `auth.uber.com`
3. DNS resolution working

### Redirect URI Mismatch

**Error in Uber response:**
```json
{
  "error": "invalid_grant",
  "error_description": "redirect_uri does not match"
}
```

**Fix:**
1. Check exact URL in Cloud Run: `UBER_REDIRECT_URI`
2. Check exact URL in Uber Developer Dashboard
3. Ensure they match exactly (case-sensitive, include path)

## Integration with Webhooks

**Important:** OAuth and webhooks work independently:

- **OAuth endpoints** (`/uber/authorize`, `/uber/callback`): Used once during setup
- **Webhook endpoint** (`/uber-webhook`): Used continuously for data sync

**Typical setup flow:**

1. Deploy service to Cloud Run ✓
2. Configure webhook URL in Uber Dashboard ✓
3. **NEW:** Run OAuth flow to activate integration
   - Visit `/uber/authorize`
   - Grant permissions
   - Receive success response
4. Webhooks start flowing automatically

## Production Checklist

Before going to production:

- [ ] `UBER_CLIENT_ID` added to Cloud Run
- [ ] `UBER_REDIRECT_URI` added to Cloud Run (matches service URL)
- [ ] Redirect URI added to Uber Developer Dashboard
- [ ] Test `/uber/authorize` redirects to Uber
- [ ] Test `/uber/callback` with real authorization code
- [ ] Verify existing `/uber-webhook` still works
- [ ] Check logs for any errors
- [ ] Existing webhook functionality unchanged

## Future Enhancements

Currently, the OAuth flow:
- ✅ Redirects to Uber authorization
- ✅ Exchanges code for token
- ✅ Returns success response
- ❌ Does NOT store token in database
- ❌ Does NOT use token for API calls

**To add token persistence:**
1. Create `UBER_OAUTH_TOKENS` table in Snowflake
2. Store `access_token`, `refresh_token`, `expires_at`
3. Use token for Uber API calls (e.g., fetch reports manually)
4. Implement token refresh logic

## Summary

The service now supports **four endpoints**:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/uber-webhook` | POST | Receive webhooks (existing) |
| `/uber/authorize` | GET | Start OAuth flow (new) |
| `/uber/callback` | GET | Complete OAuth flow (new) |

All existing functionality preserved. OAuth is additive and optional.
