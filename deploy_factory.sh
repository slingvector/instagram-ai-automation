#!/bin/bash
set -e

echo "Deploying MCR Media Factory Cloud Run Worker..."

cd src/media_factory

# Using gcloud run deploy which builds the container natively via Cloud Build
gcloud run deploy mcr-media-factory \
  --source=. \
  --region=us-central1 \
  --allow-unauthenticated \
  --set-env-vars=GCP_PROJECT_ID="mcr-relay-1772228380" \
  --service-account="modernos-edge-agent@mcr-relay-1772228380.iam.gserviceaccount.com" \
  --project="mcr-relay-1772228380" \
  --memory=1024Mi

echo "Cloud Run Deployment complete!"
