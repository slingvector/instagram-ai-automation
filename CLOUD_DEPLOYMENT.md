# MCR - Distributed Cloud Deployment Guide

This repository contains the architecture designed to run an endless Google Drive content pipeline in the cloud. It scrapes viral cricket shorts from YouTube and Instagram, processes them using AI, and securely pushes them to your Google Drive for easy publishing.

## Architecture Overview
**Cloud Node (VPS/Server):** Runs `scripts/daemon_post.py` via a Docker container 24/7. It acts as a resilient daemon that loops over the `bulk_post.py` pipeline at specified intervals (e.g., fetching 10 videos every hour).

## Step 1: Deploying the Cloud Node (VPS)

You will need a cloud VPS (e.g., AWS EC2, DigitalOcean Droplet, GCP Compute Engine). A standard $5-$10/mo Linux machine is more than sufficient.

### 1. Transfer Files
Clone this repository on your VPS and checkout the `feature/google-drive-only` branch:
```bash
git clone git@github.com:slingvector/instagram-ai-automation.git
cd instagram-ai-automation
git checkout feature/google-drive-only
```

### 2. Configure Credentials
Copy `.env.example` to `.env` on the server and fill in your details.
**CRITICAL:** Securely transfer your `modernos-edge-agent-key.json` (GCP service account key) to the root of the project on the VPS. Ensure it has access to Vertex AI, Cloud Storage, and Firestore.

### 3. Launch via Docker Compose
Ensure Docker and Docker Compose are installed on your VPS.
Boot the ingestion node daemon in the background:
```bash
docker compose -f docker-compose.ingest.yml up -d --build
```
To view the live ingestion logs and monitor the pipeline progress:
```bash
docker logs -f mcr-ingestion
```

---

## Configuration Tuning

You can adjust how the endless daemon runs by passing environment variables in your `.env` file (or hardcoding them in `docker-compose.ingest.yml`):

- `DAEMON_INTERVAL_SECONDS`: Time to sleep between full batches (Default: 3600 seconds / 1 hour)
- `REELS_PER_CYCLE`: How many reels to process in one batch (Default: 10)
- `GAP_BETWEEN_REELS`: How many seconds to wait between processing individual reels (Default: 180 seconds / 3 minutes)

---

## Production Security Considerations
- **Stateless Cloud Node:** The Cloud VPS runs headless and is entirely stateless. The `docker-compose.ingest.yml` mounts your GCP JSON key strictly as **Read-Only**.
- **Residential Proxies:** To prevent IP bans from Instagram while scraping DMs/Creators on a datacenter VPS, you should route your Playwright traffic through a Residential Proxy (you can inject proxy settings via standard Playwright kwargs in the adapters).
