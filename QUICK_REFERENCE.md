# Quick Reference: Two Uber Apps

## Credentials Overview

### App 1: Stores/Reporting (OLD - Webhook)

| Variable | Value | Source | Purpose |
|----------|-------|--------|---------|
| `UBER_CLIENT_SECRET` | (secret) | Env var / Secret Manager | Webhook HMAC verification |

**Used by:**
- POST `/uber-webhook` - Signature verification only

**Status:** ✅ Working, unchanged, safe

---

### App 2: Orders (NEW - OAuth)

| Variable | Value | Source | Purpose |
|----------|-------|--------|---------|
| `UBER_ORDERS_CLIENT_ID` | `i1KUU09cNgeeoZzzXsRK1I0ZejG-JYAd` | **Hardcoded (temp)** | OAuth authorization |
| `UBER_ORDERS_CLIENT_SECRET` | `lVetX2dHhtUliItt8tl9EtuXQ5xt5iX1abFc0cCU` | **Hardcoded (temp)** | OAuth token exchange |
| `UBER_ORDERS_REDIRECT_URI` | (TBD) | Env var | OAuth callback URL |

**Used by:**
- GET `/uber/authorize` - Start OAuth flow
- GET `/uber/callback` - Complete OAuth flow

**Status:** ✅ Isolated, no risk to webhook

---

## Code Locations

**Hardcoded credentials:** `src/main_snowflake.py` lines 66-68

```python
UBER_ORDERS_CLIENT_ID = "i1KUU09cNgeeoZzzXsRK1I0ZejG-JYAd"  # TODO: Move to env var
UBER_ORDERS_CLIENT_SECRET = "lVetX2dHhtUliItt8tl9EtuXQ5xt5iX1abFc0cCU"  # TODO: Move to env var
```

**Webhook verification:** `src/main_snowflake.py` line 718
```python
signature_valid = verify_signature(raw_body, x_uber_signature, UBER_CLIENT_SECRET)
```

**OAuth token exchange:** `src/main_snowflake.py` lines 506-510
```python
payload = {
    "client_id": UBER_ORDERS_CLIENT_ID,  # NEW
    "client_secret": UBER_ORDERS_CLIENT_SECRET,  # NEW
    ...
}
```

---

## Deployment Instructions

### Deploy with New Code

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe uber-eats-webhook-verifier \
  --region us-central1 \
  --format="value(status.url)")

# Deploy (only add new env var)
gcloud run deploy uber-eats-webhook-verifier \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars UBER_ORDERS_REDIRECT_URI=${SERVICE_URL}/uber/callback
```

**Note:** Only adding `UBER_ORDERS_REDIRECT_URI`. All old env vars/secrets unchanged.

---

## Uber Developer Dashboard Setup

### Dashboard 1: Stores/Reporting App (OLD)

**No changes needed** ✅

- Webhook URL: `https://your-service.run.app/uber-webhook` (unchanged)
- Client Secret: Still in Secret Manager (unchanged)

### Dashboard 2: Orders App (NEW)

**Add redirect URI:**

1. Go to Orders app in Uber Developer Dashboard
2. OAuth Settings → Redirect URIs
3. Add: `https://your-service.run.app/uber/callback`
4. Save

**Verify credentials match:**
- Client ID: `i1KUU09cNgeeoZzzXsRK1I0ZejG-JYAd`
- Client Secret: `lVetX2dHhtUliItt8tl9EtuXQ5xt5iX1abFc0cCU`

---

## Testing Checklist

### Test 1: Old Webhook (Should work unchanged)

```bash
# Check recent webhook logs
gcloud logging read "resource.type=cloud_run_revision AND POST /uber-webhook" --limit 5

# Look for: "✅ Signature validated, storing in Snowflake"
```

✅ Expected: Webhooks still being received and processed

### Test 2: New OAuth (Should work with Orders app)

```bash
# Visit in browser
https://your-service.run.app/uber/authorize

# Should redirect to auth.uber.com
# URL should contain: client_id=i1KUU09cNgeeoZzzXsRK1I0ZejG-JYAd
```

✅ Expected: Redirects to Uber, shows Orders app name

### Test 3: Complete OAuth Flow

1. Grant permission on Uber page
2. Redirects back to `/uber/callback?code=...`
3. Should see success JSON:

```json
{
  "status": "success",
  "message": "Authorization successful (Orders app)",
  "scope": "eats.pos_provisioning",
  "expires_in": 2592000
}
```

### Test 4: Verify Logs Show Separation

```bash
gcloud logging read "resource.type=cloud_run_revision" --limit 50 | grep -E "(Orders app|Signature validated)"
```

✅ Expected:
- Webhook logs: "✅ Signature validated" (no mention of Orders)
- OAuth logs: "Orders app" explicitly mentioned

---

## Migration to Environment Variables (Later)

When ready to move Orders credentials out of code:

### Step 1: Create Secret

```bash
echo -n "lVetX2dHhtUliItt8tl9EtuXQ5xt5iX1abFc0cCU" | \
  gcloud secrets create uber-orders-client-secret --data-file=-
```

### Step 2: Update Code (Lines 66-68)

**Change from:**
```python
UBER_ORDERS_CLIENT_ID = "i1KUU09cNgeeoZzzXsRK1I0ZejG-JYAd"  # TODO: Move to env var
UBER_ORDERS_CLIENT_SECRET = "lVetX2dHhtUliItt8tl9EtuXQ5xt5iX1abFc0cCU"  # TODO: Move to env var
```

**To:**
```python
UBER_ORDERS_CLIENT_ID = os.getenv("UBER_ORDERS_CLIENT_ID", "").strip()
UBER_ORDERS_CLIENT_SECRET = os.getenv("UBER_ORDERS_CLIENT_SECRET")
```

### Step 3: Redeploy with Env Vars

```bash
gcloud run deploy uber-eats-webhook-verifier \
  --region us-central1 \
  --set-env-vars UBER_ORDERS_CLIENT_ID=i1KUU09cNgeeoZzzXsRK1I0ZejG-JYAd \
  --update-secrets UBER_ORDERS_CLIENT_SECRET=uber-orders-client-secret:latest
```

---

## Safety Verification

### ✅ What's Safe

- OLD webhook app isolated (uses `UBER_CLIENT_SECRET`)
- NEW Orders app isolated (uses `UBER_ORDERS_CLIENT_SECRET`)
- Different variable names = no conflicts
- Different endpoints = no overlap
- Webhook signature verification unchanged

### ✅ What to Watch

After deployment, monitor:

1. **Webhook still works:**
   - Check for "✅ Signature validated" in logs
   - Check Snowflake for new rows in UBER_EATS_REPORTS

2. **OAuth flow works:**
   - Can visit `/uber/authorize` without errors
   - Redirects to Uber with correct client ID
   - Token exchange succeeds

3. **No cross-contamination:**
   - Webhook logs never mention "Orders app"
   - OAuth logs never use `UBER_CLIENT_SECRET`

---

## Endpoints Summary

| Endpoint | Method | App | Purpose |
|----------|--------|-----|---------|
| `/health` | GET | Both | Health check |
| `/uber-webhook` | GET/HEAD | Stores | URL verification |
| `/uber-webhook` | POST | Stores | Receive webhooks |
| `/uber/authorize` | GET | Orders | Start OAuth |
| `/uber/callback` | GET | Orders | Complete OAuth |

---

## Quick Answers

**Q: Will deploying this break existing webhooks?**
A: No. Webhook code is 100% unchanged.

**Q: Are the hardcoded credentials secure?**
A: For testing yes, but move to env vars/secrets before production.

**Q: Can I test without setting UBER_ORDERS_REDIRECT_URI?**
A: No. OAuth endpoints will return 500 error until you set it.

**Q: Do I need to update the OLD webhook secret?**
A: No. Never touch it. It's working fine.

**Q: Can both apps receive webhooks to the same URL?**
A: Not recommended. Webhook signatures would fail. Keep webhook URL for Stores app only.

**Q: What if I want to add webhook support for Orders app too?**
A: You'd need a second POST endpoint (e.g., `/uber-orders-webhook`) that verifies signatures using `UBER_ORDERS_CLIENT_SECRET`.

---

## Repository

**GitHub:** https://github.com/BarrysGit/uber-eats-fivetran-connector

**Key Files:**
- `src/main_snowflake.py` - Main service code
- `TWO_APPS_ANALYSIS.md` - Detailed analysis
- `OAUTH_SETUP.md` - OAuth configuration guide
- `HOW_IT_WORKS.md` - Technical architecture
