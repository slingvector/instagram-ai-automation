# Google Cloud Platform (GCP) Setup Guide

This guide covers the manual provisioning steps for Epic 1 of the ModernOS Content Relay (MCR) pipeline. Since `gcloud` is not locally installed on this Edge Mac Mini, please follow these steps from the [Google Cloud Console](https://console.cloud.google.com/).

## MCR-101: Initialize Project & APIs
1. **Create a Project:** In the top navigation bar, click the Project Dropdown and select **New Project**. Name it `modernos-relay`.
2. **Enable Billing:** Ensure a billing account is linked to this project.
3. **Enable APIs:** Navigate to **APIs & Services > Library** and enable the following:
   - `Vertex AI API`
   - `Cloud Run API`
   - `Cloud Functions API`
   - `Firestore API`
   - `Cloud Storage API`

## MCR-102: Provision Storage & Database
1. **Cloud Storage (Raw Input):**
   - Go to **Cloud Storage > Buckets** and click **Create**.
   - Name: `mcr-raw-input` (names must be globally unique, you might need to add a random suffix like `mcr-raw-input-123`).
   - Region: `us-central1`.
   - Click **Create**.
2. **Cloud Storage (Processed Output):**
   - Repeat the step above and name the second bucket `mcr-processed-output`.
3. **Firestore Database:**
   - Go to **Firestore** in the navigation menu.
   - Click **Create Database**.
   - Select **Native Mode**.
   - Choose `us-central1` as the location.
   - Start a new collection named `job_queue`.

## MCR-103: Edge-to-Cloud Security
1. **Create Service Account:**
   - Go to **IAM & Admin > Service Accounts**.
   - Click **Create Service Account**. Name it `modernos-edge-agent`.
2. **Assign Roles:**
   - Grant the following roles:
     - `Storage Object Admin`
     - `Cloud Datastore User` (for Firestore)
     - `Vertex AI User`
3. **Generate Key:**
   - Click on the newly created Service Account.
   - Go to the **Keys** tab -> **Add Key** -> **Create new key**.
   - Choose **JSON** type.
   - The key will download to your local machine.
4. **Final Step:** Move the JSON downloaded key securely to your Mac Mini and set the environment variable in your `.env` file like this:
   `GOOGLE_APPLICATION_CREDENTIALS="/Users/cortex/path/to/key.json"`
