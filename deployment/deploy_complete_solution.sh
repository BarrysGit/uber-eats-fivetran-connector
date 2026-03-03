#!/bin/bash
# Deploy Uber Eats Report Generator Job + Cloud Scheduler
# This eliminates the need for Fivetran - full end-to-end automation

set -e

PROJECT_ID="cat-database-478219"
REGION="us-east1"
JOB_NAME="uber-eats-report-generator"
IMAGE_TAG="us-east1-docker.pkg.dev/cat-database-478219/uber-eats-webhook/uber-eats-report-generator:latest"
SCHEDULER_NAME="uber-eats-daily-reports"

# Uber API credentials
UBER_CLIENT_ID="ypYKCyBCZRYqzkJRfUmE7vBPGxrru5yk"

echo "🚀 Deploying Uber Eats Report Generator Job"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Set project
gcloud config set project $PROJECT_ID

# Step 1: Create UBER_CLIENT_ID secret (if doesn't exist)
echo "📝 Step 1: Creating UBER_CLIENT_ID secret..."
echo -n "$UBER_CLIENT_ID" | gcloud secrets create UBER_CLIENT_ID \
  --data-file=- --replication-policy="automatic" --project=$PROJECT_ID 2>/dev/null || echo "Secret already exists"

# Step 2: Build Docker image for the job
echo ""
echo "🏗️  Step 2: Building Docker image for report generator..."
cd /Users/amreshsingh/Documents/GitHub/Custom_connectors/uber-eats/webhook-verifier-python

gcloud builds submit \
  --config=cloudbuild-job.yaml \
  --project=$PROJECT_ID

# Step 3: Create Cloud Run Job
echo ""
echo "🚀 Step 3: Creating/Updating Cloud Run Job..."
gcloud run jobs deploy $JOB_NAME \
  --image $IMAGE_TAG \
  --region $REGION \
  --project=$PROJECT_ID \
  --set-secrets="UBER_CLIENT_ID=UBER_CLIENT_ID:latest,UBER_CLIENT_SECRET=UBER_CLIENT_SECRET:latest,SNOWFLAKE_USER=SNOWFLAKE_USER:latest,SNOWFLAKE_ACCOUNT=SNOWFLAKE_ACCOUNT:latest,SNOWFLAKE_WAREHOUSE=SNOWFLAKE_WAREHOUSE:latest,SNOWFLAKE_PRIVATE_KEY=SNOWFLAKE_PRIVATE_KEY:latest,SNOWFLAKE_PASSWORD=SNOWFLAKE_PASSWORD:latest" \
  --memory 1Gi \
  --task-timeout 600s \
  --max-retries 1

# Step 4: Test the job (execute once manually)
echo ""
echo "🧪 Step 4: Testing job with manual execution..."
gcloud run jobs execute $JOB_NAME \
  --region $REGION \
  --project=$PROJECT_ID \
  --wait

# Step 5: Create Cloud Scheduler (daily at 7 AM Central = 1 PM UTC in winter, 12 PM UTC in summer)
# Using 1 PM UTC (7 AM Central Standard Time)
echo ""
echo "⏰ Step 5: Setting up Cloud Scheduler (daily at 7 AM Central)..."

# Delete existing scheduler if it exists
gcloud scheduler jobs delete $SCHEDULER_NAME \
  --location=$REGION \
  --project=$PROJECT_ID \
  --quiet 2>/dev/null || echo "No existing scheduler to delete"

# Create new scheduler
gcloud scheduler jobs create http $SCHEDULER_NAME \
  --location=$REGION \
  --schedule="0 13 * * *" \
  --time-zone="America/Chicago" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
  --http-method=POST \
  --oauth-service-account-email="${PROJECT_ID}@appspot.gserviceaccount.com" \
  --project=$PROJECT_ID

echo ""
echo "✅ Deployment Complete!"
echo ""
echo "📊 What was deployed:"
echo "  1. Cloud Run Job: $JOB_NAME"
echo "     - Fetches stores from Uber API"
echo "     - Triggers report generation"
echo "     - Runs daily at 7 AM Central Time"
echo ""
echo "  2. Cloud Scheduler: $SCHEDULER_NAME"
echo "     - Schedule: Daily at 7 AM Central"
echo "     - Cron: 0 13 * * * (America/Chicago)"
echo ""
echo "🔄 Complete Flow:"
echo "  1. [7 AM] Scheduler triggers job"
echo "  2. [Job] Fetches stores → stores in UBER_EATS_STORES"
echo "  3. [Job] Triggers report → gets workflow_id"
echo "  4. [Later] Uber sends webhook → webhook receiver downloads CSV"
echo "  5. [Receiver] Stores data in UBER_EATS_REPORTS + UBER_EATS_REPORT_DATA"
echo ""
echo "🎯 Fivetran is now ELIMINATED - fully automated!"
echo ""
echo "Next steps:"
echo "  - Check job logs: gcloud run jobs executions list $JOB_NAME --region $REGION"
echo "  - Check scheduler: gcloud scheduler jobs describe $SCHEDULER_NAME --location $REGION"
echo "  - Verify data: SELECT * FROM PC_FIVETRAN_DB.UBER_EATS.UBER_EATS_STORES"
