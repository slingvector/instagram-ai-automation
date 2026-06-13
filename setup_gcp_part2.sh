#!/bin/bash
set -e

PROJECT_ID="mcr-relay-1781190111"
echo "Resuming setup for Project $PROJECT_ID..."
gcloud config set project $PROJECT_ID

echo "Creating Firestore Database..."
gcloud firestore databases create --location=us-central1 --type=firestore-native || true

echo "Setting up Service Account..."
SA_NAME="modernos-edge-agent"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create $SA_NAME --display-name="MCR Edge Agent" || true

echo "Assigning IAM Roles..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/datastore.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/aiplatform.user"

echo "Downloading JSON Key..."
gcloud iam service-accounts keys create ${SA_NAME}-key.json \
    --iam-account=$SA_EMAIL

echo "Automated Setup Complete!"
echo "PROJECT_ID=$PROJECT_ID"
echo "KEY_FILE=$(pwd)/${SA_NAME}-key.json"
