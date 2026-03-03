# Draft Email to Uber Eats Support

---

**Subject:** Uber Case #51364932 - Webhook Integration Complete, Not Receiving POST Events

**To:** eats-partner-tech-support@uber.com  
**Cc:** marnaout@uber.com, kelleigh@barrys.com, p.ramsey@barrys.com, thiripura@myprecisionit.com

---

Hi Uber GTS Team,

Thank you for your previous confirmation (February 2, 2026) regarding the webhook signature verification. We have now fully implemented the webhook receiver based on your specifications and need your help confirming webhook delivery is enabled for our application.

## What We've Implemented

Based on your confirmation that **X-Uber-Signature is an HMAC SHA-256 hash over the raw request body, encoded in lowercase hexadecimal, using the application client secret**, we have:

1. **Deployed a dedicated webhook receiver** to Cloud Run:
   - URL: `https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook`
   - Service is live and reachable (returns 200 OK)
   - Health check endpoint: `https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/health`

2. **Implemented signature verification** exactly as specified:
   - HMAC-SHA256 hash computation
   - Raw request body bytes (not parsed JSON)
   - Application client secret as the signing key
   - Lowercase hexadecimal encoding
   - Constant-time comparison to prevent timing attacks

3. **Configured Uber Developer Dashboard**:
   - **Client ID:** `ypYKCyBCZRYqzkJRfUmE7vBPGxrru5yk`
   - **Primary Webhook URL:** `https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook`
   - Webhook URL was updated in the dashboard on **February 9, 2026**

4. **Response format**:
   - Returns HTTP 200 with empty response body (per Uber documentation)
   - Handles 502 on write failures (triggers Uber retry logic)

## Current Issue

Our webhook receiver is deployed and operational, but **we are not receiving any POST requests from Uber** for webhook events.

### What We See in Logs:
- ✅ Service starts successfully and connects to our database
- ✅ GET/HEAD requests to `/uber-webhook` return 200 OK (dashboard verification)
- ❌ **No POST requests** from Uber (no `orders.notification`, `orders.cancel`, `eats.report.success`, or any other webhook events)

### What We've Verified:
- ✅ Webhook URL is correct and publicly accessible
- ✅ Service accepts POST requests (GET/HEAD are also supported for URL verification)
- ✅ Client secret matches what's shown in the dashboard for this Client ID
- ✅ Signature verification code matches your specifications exactly
- ✅ Service returns proper HTTP 200 + empty body on success

## Questions / Request for Help

Could you please help us confirm the following:

1. **Webhook Delivery Enabled:**
   - Are webhooks enabled and actively sending events for Client ID `ypYKCyBCZRYqzkJRfUmE7vBPGxrru5yk`?
   - Do we need any additional approval or configuration beyond setting the Primary Webhook URL?

2. **Delivery Attempts:**
   - Can you check your logs to see if Uber has attempted to send any webhooks to our current URL (`https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook`)?
   - If there were failed delivery attempts, could you provide error details or correlation IDs?

3. **Event Types:**
   - Which webhook event types are enabled for our application?
   - We expect: `orders.notification`, `orders.cancel`, `eats.report.success`, `store.status.changed` (and others as applicable)

4. **Testing:**
   - Is there a way to trigger a test webhook event from your side?
   - Or do we need to perform a specific action (e.g., place a test order, generate a report) to trigger webhook delivery?

## Technical Details for Your Reference

**App Information:**
- **Client ID:** `ypYKCyBCZRYqzkJRfUmE7vBPGxrru5yk`
- **Organization:** Barry's
- **Scopes:** `eats.report`, `eats.store` (previously confirmed as enabled)

**Webhook Endpoint:**
- **Current Primary Webhook URL:** `https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook`
- **Last Updated:** February 9, 2026
- **HTTP Methods Supported:** POST (primary), GET/HEAD (for URL verification)
- **Expected Response:** HTTP 200 with empty body
- **Signature Verification:** HMAC-SHA256, lowercase hex, raw body, client secret

**Example Store UUID (for testing):**
- `ad2e72b9-e94d-5cb3-9675-51b7854711f3` (if you need to trigger a test event)

## Next Steps

We are ready to receive webhooks and have verified our implementation is correct per your specifications. We just need confirmation that webhook delivery is enabled and events are being sent to our endpoint.

If you need us to perform any specific action (place a test order, generate a test report, etc.) to trigger a webhook event, please let us know and we will do so immediately.

Thank you for your continued support.

Best regards,

**Amresh Singh**  
Software Engineer  
PrecisionIT  
amresh@myprecisionit.com
