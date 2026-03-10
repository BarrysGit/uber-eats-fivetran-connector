# 🔍 "Invalid client" Troubleshooting

## ✅ Credentials Are Correct

The credentials in the code match what you provided:
- Client ID: `i1KUU09cNgeeoZzzXsRK1I0ZejG-JYAd` ✅
- Client Secret: `lVetX2dHhtUliItt8tl9EtuXQ5xt5iX1abFc0cCU` ✅

## 🎯 Most Likely Causes

### Cause 1: OAuth Not Enabled in Uber Dashboard

**Check in Uber Dashboard (Barrys_Reporting app):**
- Look for "OAuth" toggle or checkbox
- Make sure it's **ON/Enabled**
- Some apps have OAuth disabled by default

### Cause 2: Scope Not Approved

**The scope `eats.pos_provisioning` might need Uber approval**

**Check:**
- Go to "Scopes" or "Permissions" section
- See if `eats.pos_provisioning` is listed
- Check if it says "Pending" or "Approved"
- If pending, you need to wait for Uber to approve

### Cause 3: Wrong App Type

**Check app type:**
- Should be "Server-side" or "Web Application"
- NOT "Client-side" or "Mobile"

### Cause 4: Redirect URI Not Matching

**Even though you added it, check:**
- Is there a typo?
- Did you click Save?
- Is it visible in the list now?

---

## 🧪 Try This Instead

### Test with Uber's Basic Scope First

Maybe try a simpler scope that doesn't need approval.

**Can you tell me:**
1. What scopes are listed in your Uber Dashboard?
2. Which ones show "Approved" or "Active"?

Then I can update the code to use an approved scope for testing.

---

## 🎯 Or Try Browser Flow

**Open in browser:**
```
https://uber-eats-webhook-verifier-330826313616.us-east1.run.app/uber/authorize
```

**What happens?**
- Does it redirect to Uber?
- Do you see login page?
- Do you see permission grant screen?
- Where exactly does the error appear?

This will help me identify the exact issue!

---

## 📸 What Would Help

Take a screenshot of:
1. The Uber Dashboard page scrolled to show "Scopes" section
2. Or the full error page when you try to authorize

Then I can see exactly what's configured and fix it!
