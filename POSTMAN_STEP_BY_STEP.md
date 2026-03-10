# 🎯 Postman Testing - Step by Step

## Test 1: Health Check ✅

**Method:** `GET`

**URL:**
```
https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/health
```

**Headers:** None needed

**Body:** None

**Expected Response:**
```json
{
  "status": "ok",
  "snowflake": "connected"
}
```

**Status Code:** `200 OK`

---

## Test 2: Webhook GET (Uber Validation) ✅

**Method:** `GET`

**URL:**
```
https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook
```

**Headers:** None needed

**Body:** None

**Expected Response:** Empty (no body)

**Status Code:** `200 OK`

---

## Test 3: Webhook POST - Invalid Signature (Security Test) ❌

**Method:** `POST`

**URL:**
```
https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook
```

**Headers:**
```
Content-Type: application/json
X-Uber-Signature: invalid_test_signature
```

**Body (raw JSON):**
```json
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

**Status Code:** `401 Unauthorized`

**Purpose:** Proves signature verification is working (this should fail!)

---

## Test 4: OAuth Authorize (Check Redirect) 🔄

**Method:** `GET`

**URL:**
```
https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber/authorize
```

**Headers:** None needed

**Body:** None

**In Postman:**
1. Click **Send**
2. Look at **Status Code**: Should be `307 Temporary Redirect`
3. Click **Headers** tab in response
4. Find `Location` header
5. Should contain: `https://auth.uber.com/oauth/v2/authorize?client_id=i1KUU09cNgeeoZzzXsRK1I0ZejG-JYAd...`

**Expected Response:** Redirect response (307)

**Location Header Should Contain:**
- `auth.uber.com`
- `client_id=i1KUU09cNgeeoZzzXsRK1I0ZejG-JYAd`
- `redirect_uri=https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber/callback`
- `scope=eats.pos_provisioning`

---

## Test 5: OAuth Callback - No Code ❌

**Method:** `GET`

**URL:**
```
https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber/callback
```

**Headers:** None needed

**Body:** None

**Expected Response:**
```json
{
  "error": "missing_authorization_code",
  "message": "Authorization code is required"
}
```

**Status Code:** `400 Bad Request`

**Purpose:** Shows callback validation is working

---

## Test 6: OAuth Callback - Fake Code (Will Try to Exchange) ❌

**Method:** `GET`

**URL:**
```
https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber/callback?code=fake_test_code_12345
```

**Headers:** None needed

**Body:** None

**Expected Response:**
```json
{
  "error": "token_exchange_failed",
  "uber_status_code": 400,
  "uber_response": "invalid_grant"
}
```

**Status Code:** `502 Bad Gateway`

**Purpose:** Shows token exchange logic is working (fails because code is fake)

---

## 🎊 Test 7: REAL OAuth Flow (Browser Required)

**This one needs a browser, but I'll show you how to capture the code for Postman:**

### Step A: Get Authorization URL from Postman

**Method:** `GET`

**URL:**
```
https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber/authorize
```

1. Send request in Postman
2. Look at response **Headers** tab
3. Copy the full URL from `Location` header
4. Open that URL in your browser

### Step B: Complete OAuth in Browser

1. Login to Uber
2. Click "Allow" on permission screen
3. You'll be redirected to: `...uber/callback?code=ABC123XYZ...`
4. **Copy the code from the URL** (everything after `code=`)

### Step C: Test Token Exchange in Postman

**Method:** `GET`

**URL:**
```
https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber/callback?code=PASTE_REAL_CODE_HERE
```

Replace `PASTE_REAL_CODE_HERE` with the code you copied in Step B.

**Expected Response (Success!):**
```json
{
  "status": "success",
  "message": "Authorization successful (Orders app)",
  "scope": "eats.pos_provisioning",
  "expires_in": 2592000
}
```

**Status Code:** `200 OK`

**⚠️ Note:** Authorization codes expire in 10 minutes, so test quickly after getting the code!

---

## 📋 Quick Reference Table

| Test | Method | URL | Headers | Body | Expected Status |
|------|--------|-----|---------|------|-----------------|
| 1. Health | GET | `/health` | None | None | 200 |
| 2. Webhook GET | GET | `/uber-webhook` | None | None | 200 |
| 3. Webhook POST Invalid | POST | `/uber-webhook` | See Test 3 | See Test 3 | 401 |
| 4. OAuth Authorize | GET | `/uber/authorize` | None | None | 307 |
| 5. Callback No Code | GET | `/uber/callback` | None | None | 400 |
| 6. Callback Fake Code | GET | `/uber/callback?code=fake` | None | None | 502 |
| 7. Callback Real Code | GET | `/uber/callback?code=REAL` | None | None | 200 |

---

## 🎨 Postman Setup Screenshots

### For Test 3 (Webhook POST):

**Request Setup:**
```
Method: POST
URL: https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook
```

**Headers Tab:**
```
Key: Content-Type     Value: application/json
Key: X-Uber-Signature Value: invalid_test_signature
```

**Body Tab:**
- Select: `raw`
- Format: `JSON`
- Content:
```json
{
  "event_id": "test_event_123",
  "event_type": "eats.report.success",
  "report_type": "EATS_STORE_DAILY_SALES_SUMMARY_REPORT_V2",
  "test": true
}
```

---

## ✅ Tests You Can Run Right Now (No Browser)

### Quick 5-Minute Test

1. **Test 1** - Health Check → Should get 200 with Snowflake status ✅
2. **Test 2** - Webhook GET → Should get 200 empty ✅
3. **Test 3** - Webhook POST invalid → Should get 401 ✅
4. **Test 4** - OAuth authorize → Should get 307 redirect ✅
5. **Test 5** - Callback no code → Should get 400 error ✅

**All 5 should pass!** This proves your service is working.

---

## 🎯 Base URL Variable (Optional)

If you want to make it easier in Postman:

1. Click collection (top level)
2. Go to **Variables** tab
3. Add variable:
   - **Variable:** `base_url`
   - **Value:** `https://uber-eats-webhook-verifier-330826313616.us-east1.run.app`
4. Then use: `{{base_url}}/health` in requests

---

## 📦 Import My Pre-Made Collection

**File location:**
```
/Users/amreshsingh/Documents/GitHub/Custom_connectors/uber-eats/webhook-verifier-python/Uber_Eats_Postman_Collection.json
```

**Or download from GitHub:**
```
https://raw.githubusercontent.com/BarrysGit/uber-eats-fivetran-connector/main/Uber_Eats_Postman_Collection.json
```

This has all 8 tests pre-configured! Just import and click Send on each.

Let me know which test you want to run first! 🚀
