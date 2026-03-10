#!/bin/bash

# Complete OAuth Setup Script
# Run this in your terminal after gcloud auth login

set -e  # Exit on error

echo "🔍 Finding your Cloud Run service..."
echo ""

# Try to find the service in common regions
SERVICE_URL=""
REGION=""

for region in us-east1 us-central1 us-west1 europe-west1; do
  echo "Checking region: $region..."
  URL=$(gcloud run services describe uber-eats-webhook-verifier --region $region --format="value(status.url)" 2>/dev/null || echo "")
  if [ -n "$URL" ]; then
    SERVICE_URL="$URL"
    REGION="$region"
    echo "✅ Found service in $region"
    break
  fi
done

if [ -z "$SERVICE_URL" ]; then
  echo "❌ Service not found in common regions. Listing all services:"
  echo ""
  gcloud run services list
  echo ""
  echo "Please find your uber-eats-webhook-verifier service and run:"
  echo "export SERVICE_URL=<your-service-url>"
  echo "export REGION=<your-region>"
  echo "Then run this script again."
  exit 1
fi

echo ""
echo "📍 Service Details:"
echo "   URL: $SERVICE_URL"
echo "   Region: $REGION"
echo ""

# Set redirect URI
REDIRECT_URI="${SERVICE_URL}/uber/callback"

echo "🔧 Setting UBER_ORDERS_REDIRECT_URI..."
gcloud run services update uber-eats-webhook-verifier \
  --region $REGION \
  --set-env-vars UBER_ORDERS_REDIRECT_URI=$REDIRECT_URI

echo ""
echo "✅ Environment variable set!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 NEXT STEPS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1️⃣  Add to Uber Developer Dashboard (Orders App):"
echo ""
echo "    Go to: https://developer.uber.com/"
echo "    → Select Orders App"
echo "    → OAuth Settings → Redirect URIs"
echo "    → Add: $REDIRECT_URI"
echo "    → Save"
echo ""
echo "2️⃣  Test OAuth flow (open in browser):"
echo ""
echo "    ${SERVICE_URL}/uber/authorize"
echo ""
echo "3️⃣  Test webhook still works:"
echo ""
echo "    curl ${SERVICE_URL}/health"
echo ""
echo "4️⃣  Check logs:"
echo ""
echo "    gcloud logging read \"resource.type=cloud_run_revision\" --region $REGION --limit 20"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
