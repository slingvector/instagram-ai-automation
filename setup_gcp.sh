#!/bin/bash
set -e

PROJECT_ID="mcr-relay-$(date +%s)"
BILLING_ACCT="01B708-8E9317-E82038"

echo "Creating project $PROJECT_ID..."
gcloud projects create $PROJECT_ID --name="ModernOS Content Relay"

echo "Setting project..."
gcloud config set project $PROJECT_ID

echo "Linking billing account..."
gcloud beta billing projects link $PROJECT_ID --billing-account=$BILLING_ACCT

echo "Enabling APIs..."
gcloud services enable aiplatform.googleapis.com \
                       run.googleapis.com \
                       cloudfunctions.googleapis.com \
                       firestore.googleapis.com \
                       storage.googleapis.com

echo "Creating Storage Buckets..."
gsutil mb -p $PROJECT_ID -l us-central1 "gs://${PROJECT_ID}-raw-input"
gsutil mb -p $PROJECT_ID -l us-central1 "gs://${PROJECT_ID}-processed-output"

echo "Creating Firestore Database..."
gcloud firestore databases create --location=us-central1 --type=firestore-native

echo "Setting up Service Account..."
SA_NAME="modernos-edge-agent"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create $SA_NAME --display-name="MCR Edge Agent"

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
