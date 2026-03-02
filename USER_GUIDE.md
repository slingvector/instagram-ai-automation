# User Guide: MCR Instagram Automation Pipeline

Welcome to the ModernOS Content Relay (MCR) Instagram Automation Pipeline. This guide covers how to set up, configure, and run the end-to-end ingestion and publishing architecture.

---

## 1. Architecture Overview
This system is composed of two heavily decoupled environments:
1. **The Ingestion Layer (MacOS/Server)**
   - Monitors Instagram DMs, specific Creators, trending Reddit/RSS topics, and cross-platform feeds.
   - Powered by `yt-dlp` for media extraction and `APScheduler` for concurrent daemon execution.
   - Pushes raw assets to Google Cloud Storage (GCS) and Firestore.
2. **The Publishing Edge (Appium Docker + Physical Android)**
   - Listens to Firestore for pending jobs.
   - Connects to an Android device (via USB or WiFi ADB) running Instagram.
   - Automates the physical Reel upload UI via Appium UIAutomator2.

---

## 2. Prerequisites
- **Python 3.11+** installed on the host machine.
- **Docker Desktop** (or equivalent Engine) for running the Appium Server container.
- An **Android Device** (Android 11+ recommended) or Emulator with Developer Options -> USB/Wireless Debugging enabled.
- The **Instagram** Android app installed and securely logged into your target posting account.
- **Google Cloud Platform (GCP)** Service Account Key with read/write access to GCS and Firestore.

---

## 3. Initial Setup

### Step 1: Clone and Environment
1. Open terminal in the project directory.
2. Create and activate the virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

### Step 2: Configure Credentials
1. Copy the example environment file: `cp .env.example .env`
2. Open `.env` and fill out key credentials:
   - `GOOGLE_APPLICATION_CREDENTIALS`: Path to your GCP JSON key.
   - `GCP_PROJECT_ID`: Your exact GCP project name.
   - `IG_READONLY_USERNAME` / `IG_READONLY_PASSWORD`: Dedicated "burner" Instagram account used *only* for scraping DM/Creator endpoints (Do not use your main account here).

---

## 4. Connecting the Android Device

The automated publisher requires a physical Android phone or an emulator tied directly via ADB (Android Debug Bridge).

### Option A: USB Connecting
1. Connect via USB cable. Ensure "USB Debugging" is enabled on your phone.
2. Run `adb devices`. You should see `device_serial    device`.
3. In `.env`, set `DEVICE_UDID="your_device_serial"`.

### Option B: Wireless Connecting (Android 11+)
1. Ensure both your Mac and phone are on the exact same Wi-Fi network.
2. Enable "Wireless Debugging" on your phone.
3. Run the setup helper script: `./setup_adb_wireless.sh` and follow the on-screen pairing prompts.
4. Set `DEVICE_UDID="your_phone_ip:port"` (from `adb devices`) in `.env`.

---

## 5. Starting the Appium Edge Server

The Appium server runs inside a Docker container configured to share your Mac's host ADB socket.

1. Ensure the ADB server is running on the host:
   ```bash
   adb kill-server
   nohup adb -a nodaemon server start >/dev/null 2>&1 &
   ```
2. Start the Dockerized Appium server:
   ```bash
   docker compose -f docker-compose.appium.yml up -d
   ```
3. You can verify it detects your device by running:
   ```bash
   docker exec mcr-appium adb devices
   ```

---

## 6. Configuring Content Ingestion Targets

All targets that feed movies into the pipeline are located in the `config/` directory.

- **`creator_watchlist.yaml`**: Add top Instagram influencers by username here. The bot will scan their feeds for viral reels exceeding the view/like multiplier thresholds.
- **`exclusive_watchlist.yaml`**: Reserved for creator networks where 100% of their video posts should be mirrored without view-threshold filtering.
- **`trending_sources.yaml`**: Configure Subreddits (e.g., `r/funny`), global RSS news feeds, and YouTube trending endpoints here.
- **`cross_platform.yaml`**: Define specific TikTok, Shorts, or X (Twitter) profiles for direct 1-to-1 syncs.

---

## 7. Running the Pipeline

### Starting the Ingestion Master Scheduler
This process polls the platforms in the background and sends matching media payloads to Google Cloud.

```bash
source venv/bin/activate
PYTHONPATH=. python src/ingestion/scheduler.py
```
*(By default, this respects multi-hour production delays. To test rapidly, start it like so: `DEV_MODE=1 PYTHONPATH=. python src/ingestion/scheduler.py` which compresses wait times to 1-2 minutes).*

### Starting the Edge Publisher
In a separate terminal, launch the listener that drives the Appium Instagram automation:

```bash
source venv/bin/activate
PYTHONPATH=. python -c "from src.publishing_edge.services.firestore_listener_service import FirestoreListenerService; FirestoreListenerService().start()"
```
This listener will idle quietly until the Ingestion Scheduler pushes a `READY_FOR_PUBLISHING` job to Firestore, at which point it will wake the Android phone and upload the reel.

---

## 8. Human Review Feature (Default: ON)
By default, the pipeline stages drafts in the Instagram app and waits.

1. Open your GCP Firestore console -> `job_queue` collection.
2. Find the job marked `AWAITING_HUMAN_APPROVAL`.
3. Review the staged video draft on the physical phone screen.
4. If it looks perfect, edit the Firestore document status from `AWAITING_HUMAN_APPROVAL` to `APPROVED`. The Appium bot will instantly wake up and tap "Share".
5. Change it to `REJECTED` to abort and discard the draft.

*To bypass review completely for fully-automated AI pages, set `HUMAN_REVIEW_ENABLED="false"` in your `.env`.*

---

## 9. Troubleshooting
- **Playwright errors (Ingestion):** If Playwright fails to load IG, try setting `HEADLESS="False"` in `.env` and run `python test_dm_scraper.py`. This opens a visible browser so you can manually solve a CAPTCHA or confirm the login on the Read-Only account.
- **"Could not find a connected Android device" (Appium):** Your Docker container has lost sync with the host ADB socket. Rerun the two commands under Section 5 to restart the host ADB server and the docker container.
- **UI element not found (Appium):** Instagram occasionally changes its layout. Look in the `debug/` folder; the bot saves XML state dumps and screenshots (`<timestamp>_step_name.png`) exactly where it failed. Update the fallback ADB coordinates in `src/publishing_edge/services/appium_posting_service.py` if the UI buttons have moved drastically on your specific device resolution.
