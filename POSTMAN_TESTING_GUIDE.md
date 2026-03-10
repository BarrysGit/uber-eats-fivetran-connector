# Postman Testing Guide for Uber Eats Service

## 📦 Quick Import

### Option 1: Import Collection File
1. Open Postman
2. Click **Import** button (top left)
3. Select **Upload Files**
4. Choose `Uber_Eats_Postman_Collection.json`
5. Click **Import**

### Option 2: Import from URL
1. Open Postman
2. Click **Import** → **Link**
3. Paste: `https://raw.githubusercontent.com/BarrysGit/uber-eats-fivetran-connector/main/Uber_Eats_Postman_Collection.json`
4. Click **Import**

---

## 🧪 Test Requests (Copy-Paste into Postman)

### 1. Health Check ✅
**Expected: 200 OK with Snowflake status**

```
GET https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/health
```

**Expected Response:**
```json
{
  "status": "ok",
  "snowflake": "connected"
}
```

---

### 2. Webhook GET (Uber Validation Test) ✅
**Expected: 200 OK - Empty body**

```
GET https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook
```

**Expected Response:** Empty body with 200 status

**Purpose:** Uber tests this to verify your webhook URL is accessible

---

### 3. Webhook HEAD (Uber Validation Test) ✅
**Expected: 200 OK - No body**

```
HEAD https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook
```

**Expected Response:** No body, just 200 status

---

### 4. Webhook POST - Invalid Signature ❌
**Expected: 401 Unauthorized**

```
POST https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook

Headers:
Content-Type: application/json
X-Uber-Signature: invalid_signature_for_testing

Body (raw JSON):
{
  "event_id": "test_event_123",
  "event_type": "eats.report.success",
  "report_type": "EATS_STORE_DAILY_SALES_SUMMARY_REPORT_V2",
  "test": true
}
```

**Expected Response:**
```json
{
  "detail": "Invalid signature"
}
```

**Purpose:** Proves signature verification is working (security test)

---

### 5. Webhook POST - Missing Signature ❌
**Expected: 401 Unauthorized**

```
POST https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook

Headers:
Content-Type: application/json
(No X-Uber-Signature header)

Body (raw JSON):
{
  "event_id": "test_event_456",
  "event_type": "eats.report.success"
}
```

**Expected Response:**
```json
{
  "detail": "Missing signature"
}
```

---

### 6. OAuth Authorize (Will Redirect) 🔄
**Expected: 307 Redirect to auth.uber.com**

```
GET https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber/authorize
```

**In Postman:**
- Click **Send**
- Look at response **Headers**
- Find `Location` header
- Should contain: `https://auth.uber.com/oauth/v2/authorize?client_id=i1KUU09cNgeeoZzzXsRK1I0ZejG-JYAd...`

**Purpose:** Starts OAuth flow - redirects to Uber login

**To test in browser:** Copy the URL from `Location` header and open it

---

### 7. OAuth Callback - Missing Code ❌
**Expected: 400 Bad Request**

```
GET https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber/callback
```

**Expected Response:**
```json
{
  "error": "missing_authorization_code",
  "message": "Authorization code is required"
}
```

**Purpose:** Tests validation of OAuth callback

---

### 8. OAuth Callback - With Fake Code ❌
**Expected: 502 Bad Gateway (token exchange fails)**

```
GET https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber/callback?code=fake_test_code_12345
```

**Expected Response:**
```json
{
  "error": "token_exchange_failed",
  "uber_status_code": 400,
  "uber_response": "invalid_grant"
}
```

**Purpose:** Shows token exchange logic works (will fail because code is fake)

**Note:** Real OAuth flow requires going through Uber's login first

---

## 🎯 Complete OAuth Flow Test (Browser + Postman)

### Step 1: Start OAuth in Browser

Open this URL in your browser:
```
https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber/authorize
```

**You'll see:**
1. Uber login page
2. Permission grant screen
3. After clicking "Allow", redirects to callback

### Step 2: Copy the Authorization Code

After clicking "Allow", Uber redirects to:
```
https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber/callback?code=REAL_CODE_HERE
```

**Copy the `code=...` value**

### Step 3: Test in Postman with Real Code

```
GET https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber/callback?code=<PASTE_REAL_CODE_HERE>
```

**Expected Response (Success):**
```json
{
  "status": "success",
  "message": "Authorization successful (Orders app)",
  "scope": "eats.pos_provisioning",
  "expires_in": 2592000
}
```

**Note:** Authorization codes expire in ~10 minutes, so test quickly!

---

## 📊 Expected Test Results Summary

| Test # | Request | Expected Status | Purpose |
|--------|---------|----------------|---------|
| 1 | GET /health | 200 | Service health |
| 2 | GET /uber-webhook | 200 | Uber validation |
| 3 | HEAD /uber-webhook | 200 | Uber validation |
| 4 | POST /uber-webhook (invalid sig) | 401 | Security test |
| 5 | POST /uber-webhook (no sig) | 401 | Security test |
| 6 | GET /uber/authorize | 307 | OAuth start |
| 7 | GET /uber/callback | 400 | Validation test |
| 8 | GET /uber/callback?code=fake | 502 | Token exchange test |

**All should pass with expected status codes!** ✅

---

## 🔍 How to Check Responses in Postman

### For Redirects (307)
1. Send request
2. Click **Headers** tab
3. Find `Location` header
4. Copy URL to see where it redirects

### For JSON Responses
1. Send request
2. Click **Body** tab
3. Select **Pretty** view
4. Response auto-formats as JSON

### For Status Codes
1. Look at top right after sending
2. Shows status like `200 OK` or `401 Unauthorized`

---

## 🎨 Postman Collection Structure

After importing, you'll see:

```
📦 Uber Eats Fivetran Connector
  ├── 1. Health Check
  ├── 2. Webhook GET (Uber Validation)
  ├── 3. Webhook HEAD (Uber Validation)
  ├── 4. Webhook POST - Invalid Signature
  ├── 5. Webhook POST - Missing Signature
  ├── 6. OAuth Authorize (Will Redirect)
  ├── 7. OAuth Callback - Missing Code
  └── 8. OAuth Callback - With Test Code
```

---

## 🚀 Quick Test All (Postman Runner)

### Method 1: Manual Testing
1. Click each request in order (1-8)
2. Click **Send**
3. Verify expected status code

### Method 2: Collection Runner
1. Click **...** next to collection name
2. Select **Run collection**
3. Click **Run Uber Eats Fivetran Connector**
4. Watch tests execute automatically

**All requests should complete successfully!**

---

## 🔐 Testing Real Webhook with Valid Signature

To test with a valid signature, you need:

1. **Your Uber Client Secret** (for Stores/Reporting app - the OLD webhook app)
2. **The exact request body as bytes**
3. **Compute HMAC-SHA256 signature**

### Python Script to Generate Valid Signature

```python
import hmac
import hashlib
import json

# Your OLD webhook app secret (from Secret Manager)
CLIENT_SECRET = "your_uber_stores_app_client_secret_here"

# Request body (must be exact bytes)
body = {
    "event_id": "test_event_real",
    "event_type": "eats.report.success",
    "report_type": "EATS_STORE_DAILY_SALES_SUMMARY_REPORT_V2"
}

body_json = json.dumps(body, separators=(',', ':'))  # No spaces
body_bytes = body_json.encode('utf-8')

# Compute HMAC
signature = hmac.new(
    CLIENT_SECRET.encode('utf-8'),
    body_bytes,
    hashlib.sha256
).hexdigest()

print(f"Body: {body_json}")
print(f"Signature: {signature}")
```

### Then in Postman:

```
POST https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook

Headers:
Content-Type: application/json
X-Uber-Signature: <COMPUTED_SIGNATURE>

Body (raw JSON - must match exactly):
{"event_id":"test_event_real","event_type":"eats.report.success","report_type":"EATS_STORE_DAILY_SALES_SUMMARY_REPORT_V2"}
```

**Expected:** 200 OK with empty body (webhook accepted and stored in Snowflake)

---

## 📝 Notes

### Why Some Tests Fail (Expected)
- **Invalid signatures** → Should fail with 401 ✅
- **Missing authorization codes** → Should fail with 400 ✅
- **Fake authorization codes** → Should fail with 502 ✅

These failures prove security is working!

### Why OAuth Needs Browser
OAuth requires:
1. User login to Uber
2. User grants permission
3. Uber generates authorization code
4. Code sent to callback

Can't be fully tested in Postman alone (needs browser for login)

### Testing Production Webhooks
Real webhooks from Uber will:
- Have valid `X-Uber-Signature`
- Contain real event data
- Return 200 OK with empty body
- Store data in Snowflake

Monitor logs to see real webhooks:
```bash
gcloud logging read "resource.type=cloud_run_revision" --project cat-database-478219 --limit 20
```

---

## 🎊 Summary

**Import:** `Uber_Eats_Postman_Collection.json`

**Test:** Run all 8 requests in order

**Expected:** All pass with expected status codes

**OAuth:** Use browser for login, then Postman for callback test

**Repository:** https://github.com/BarrysGit/uber-eats-fivetran-connector

✅ Ready to test!
