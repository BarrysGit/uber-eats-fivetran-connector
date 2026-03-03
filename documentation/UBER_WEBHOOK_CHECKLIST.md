# Uber Eats Webhook – Double-Check Checklist

Use this to confirm everything is correct on your side before contacting Uber.

---

## 1. Our endpoint (already verified)

| Check | Status |
|-------|--------|
| **URL** | `https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook` (exact path `/uber-webhook`) |
| **Method** | POST only for real events; GET/HEAD return 200 so dashboard verification doesn’t get 405 |
| **Response** | 200 with **empty body** (per Uber docs) after storing in Snowflake |
| **Signature** | HMAC-SHA256 of body with client secret, lowercased hex; constant-time compare |
| **UBER_CLIENT_SECRET** | Must match the **Client Secret** for this app in Uber Developer Dashboard |

---

## 2. Uber Developer Dashboard

| Check | What to verify |
|-------|----------------|
| **Primary Webhook URL** | Setup → Webhooks → **Primary Webhook URL** = `https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook` (no trailing slash, correct path). |
| **Authentication** | Webhooks use **signature only** (X-Uber-Signature). If the dashboard has “Authentication Type” for webhooks, use **None** / no HTTP auth so Uber doesn’t send Basic/OAuth we don’t validate. |
| **Client Secret** | The **Client Secret** shown in the dashboard for this app is the one we use for `UBER_CLIENT_SECRET` in Cloud Run. If you rotated the secret, update the Cloud Run secret and redeploy. |
| **App / API access** | Docs say “Access may require written approval from Uber.” If the app isn’t approved for Eats or webhooks, events might not be sent. |

---

## 3. Events (why POST might never be sent)

Uber sends a **POST** only when an **event** happens. No event ⇒ no POST.

| Check | What to do |
|-------|------------|
| **Test order** | Place a **test order** on Uber Eats with your **test developer account**, delivery address = **test store address**. No payment needed. |
| **Store status** | In [Uber Eats Orders](https://restaurant-dashboard.uber.com), ensure the test store is **Accept Orders**. |
| **Service availability** | Menu’s `service_availability` should cover the time you’re testing. If the store still appears unavailable, try an incognito window. |
| **Other events** | `store.provisioned`, `store.status.changed`, etc. only fire when those actions occur. |

---

## 4. Cloud Run / network

| Check | What to verify |
|-------|----------------|
| **Invocation** | Service allows **unauthenticated** invocations (or that Uber’s requests are authenticated if you require IAM). Otherwise Uber’s POST could get 403 before hitting our code. |
| **Logs** | After a test order, run: `gcloud run services logs read uber-eats-webhook-verifier --region us-east1 --limit 50` and look for **POST** and “Received POST /uber-webhook”. |

---

## 5. If you still see no POST

- Confirm the dashboard URL and client secret (sections 1–2).
- Confirm a test order was placed and store was accepting orders (section 3).
- Check Cloud Run logs for **any** POST to `/uber-webhook` (section 4).

If all of the above are correct and you still never see a POST, it’s reasonable to contact Uber (e.g. developer support or the contact from your approval process) and ask them to confirm that webhooks are enabled for your app and that they see delivery attempts to your URL.

---

## Draft email to Uber (copy and adapt)

**Subject:** Uber Eats webhooks not receiving POST events – [Your App Name] / [Client ID]

**Body:**

Hello,

We have integrated the Uber Eats Marketplace API and configured the Primary Webhook URL in the Developer Dashboard as required:

- **Primary Webhook URL:** `https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber-webhook`
- **App / Client ID:** [insert your app name or client ID]

Our endpoint is live and we have verified:

1. The URL is reachable (GET/HEAD to the same path return 200).
2. We respond to POST with HTTP 200 and an empty body after processing, per the webhook documentation.
3. We verify the `X-Uber-Signature` header (HMAC-SHA256 with our client secret).
4. The Client Secret in our deployment matches the one shown in the dashboard for this app.

We have placed test orders and ensured our test store is set to “Accept Orders,” but we do not see any **POST** requests to our webhook in our logs—only our own GET/HEAD checks.

Could you please confirm:

1. That webhooks are enabled for our application (and that no extra approval or configuration is needed for webhook delivery)?
2. Whether your systems show any delivery attempts (success or failure) to the above webhook URL for our app?
3. Any required steps we might be missing (e.g. store provisioning, environment, or dashboard settings) for webhook events to be sent?

Thank you,

[Your name / team]

---

*After deploying the latest code (empty 200 body + GET/HEAD handlers), redeploy the Cloud Run service and then run through this checklist and, if needed, send the draft email.*
