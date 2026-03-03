# MCR - Distributed Cloud Deployment Guide

This branch (`cloud-ready`) contains the architecture designed to break the MCR pipeline into two separate, highly scalable components: a Cloud Ingestion Node and a Local Publishing Edge.

## Architecture Overview
1. **Cloud Ingestion Node (VPS/Server):** Runs the heavy `scheduler.py` via a Docker container 24/7. It scrapes platforms, normalizes videos, and uploads media to Google Cloud Storage (GCS).
2. **Local Publishing Edge (Mac Mini + Phone):** Runs `firestore_listener_service.py` via a macOS native background daemon. It silently waits for jobs in Firestore and executes physical Appium posts on the connected Android device.

## Step 1: Deploying the Cloud Ingestion Node (VPS)

You will need a cloud VPS (e.g., AWS EC2, DigitalOcean Droplet, GCP Compute Engine). A standard $5-$10/mo Linux machine is more than sufficient.

### 1. Transfer Files
Clone this repository on your VPS and checkout the `cloud-ready` branch:
```bash
git clone git@github.com:slingvector/instagram-ai-automation.git
cd instagram-ai-automation
git checkout cloud-ready
```

### 2. Configure Credentials
Copy `.env.example` to `.env` on the server and fill in your details.
**CRITICAL:** Securely transfer your `modernos-edge-agent-key.json` (GCP service account key) to the root of the project on the VPS.

### 3. Launch via Docker Compose
Ensure Docker and Docker Compose are installed on your VPS.
Boot the ingestion node daemon in the background:
```bash
docker compose -f docker-compose.ingest.yml up -d --build
```
To view the live ingestion logs:
```bash
docker logs -f mcr-ingestion
```

---

## Step 2: Setting up the Local Publishing Edge (Mac Mini)

Your Mac Mini is responsible for the actual Instagram App automation. It does not need to run the scheduler; it just listens to the centralized Firestore job queue.

### 1. Prepare the Mac Environment
Ensure your phone is connected via USB or Wireless ADB (`adb devices` must show the device). Ensure your local Mac Mini is checked out to the `cloud-ready` branch.

### 2. Install the macOS Autostart Daemon
We have included a script that registers the publisher as a persistent macOS Background Service. It will automatically restart the ADB daemon, boot the Appium Docker container, and attach the Python listener every time the Mac Mini boots up.

Open a terminal on your Mac Mini and run:
```bash
chmod +x tools/install_mac_autostart.sh
./tools/install_mac_autostart.sh
```

### 3. Managing the Edge Daemon
- **Check Logs:** `tail -f data/edge_service.out` (and `data/edge_service.err`)
- **Stop Service manually:** `launchctl unload ~/Library/LaunchAgents/com.mcr.publishing.edge.plist`
- **Start Service manually:** `launchctl load ~/Library/LaunchAgents/com.mcr.publishing.edge.plist`

---

## Production Security Considerations
- **Stateless Cloud Node:** The Cloud VPS runs headless and is entirely stateless. The `docker-compose.ingest.yml` mounts your GCP JSON key strictly as **Read-Only**.
- **Residential Proxies:** To prevent IP bans from Instagram while scraping DMs/Creators on a datacenter VPS, you should route your Playwright traffic through a Residential Proxy (you can inject proxy settings via standard Playwright kwargs in the adapters).
