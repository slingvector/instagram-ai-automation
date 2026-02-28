#!/bin/bash
set -e

# Deploy the Python 3.11 Cloud function using Gen 2
echo "Deploying MCR Video Ingestion Cloud Function..."

cd src/cloud_function

gcloud functions deploy mcr-video-ingest \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=ingest_video \
  --trigger-http \
  --allow-unauthenticated \
  --memory=512MB \
  --set-build-env-vars=BUSTER=$(date +%s) \
  --set-env-vars=GCP_PROJECT_ID="mcr-relay-1772228380" \
  --service-account="modernos-edge-agent@mcr-relay-1772228380.iam.gserviceaccount.com" \
  --project="mcr-relay-1772228380"

echo "Deployment complete!"
