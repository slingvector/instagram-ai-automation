# Instagram AI Automation (V2 Pipeline)

> **ModernOS Content Relay (MCR)** — An automated Instagram Reel ingestion and processing pipeline.

## What It Does

1. **Precision Targeting**: Harvests reels directly from targeted creators via curated manifests (e.g., `config/fashion_manifest.yaml`).
2. **AI Action-Zone Cropping**: Uses Vertex AI to analyze landscape videos and intelligently re-frame the primary subject to a native 9:16 portrait cut.
3. **Kinetic Typography**: Generates word-level timestamps and cinematic kinetic captions using FFmpeg.
4. **Relay Engine**: Sends processed videos securely to your phone via local Wi-Fi (LocalSend) or to Firebase Storage for CDN delivery.
5. **Dashboard**: A gorgeous Next.js GUI for manually reviewing and approving videos.

---

## 🚀 Easy Local Setup (Docker Compose)

The easiest way to run the pipeline without installing Python, Node.js, FFmpeg, or browser drivers on your host machine is via Docker Compose.

### Prerequisites
- Docker & Docker Compose installed.
- A valid `.env` file with your GCP / Firebase credentials.

### Instructions

1. **Clone the Repository**
2. **Set up credentials**
   ```bash
   cp .env.example .env
   # Ensure your google service account JSON is placed in the project root
   ```
3. **Boot the Pipeline & Dashboard**
   ```bash
   docker-compose up -d
   ```

This will automatically:
- Start the `backend` Python container which continuously scrapes and processes videos into the `./data` directory.
- Start the `dashboard` Next.js container on port `3000`.

You can now view your dashboard locally at: [http://localhost:3000](http://localhost:3000)

---

## 🌍 Remote Access (View Dashboard Anywhere)

If you are running the Docker Compose stack on your Mac or a local server, and want to access the Dashboard securely from your phone or while traveling, use a **Cloudflare Tunnel**. It is completely free and requires zero router configuration.

### Cloudflare Tunnel Setup (1-Click)

Run this command in a new terminal window on the machine running Docker:

```bash
cloudflared tunnel --url http://localhost:3000
```

*(If you don't have `cloudflared` installed, install it via `brew install cloudflare/cloudflare/cloudflared` on Mac or download the binary).*

Cloudflare will instantly output a secure, public HTTPS URL (e.g., `https://random-words.trycloudflare.com`). 
You can visit this URL on any device anywhere in the world, and it will securely route to your local dashboard and video files!

---

## Architecture Overview

```
[Target Manifests]
    │
    ▼
[Backend Container] (Python)
    ├── Scrape & Download 
    ├── AI Reframe (Vertex AI)
    ├── Transcribe & Burn (FFmpeg)
    └── Write to SQLite DB
    │
    ▼
[Shared Volume] (./data)
    │
    ▼
[Dashboard Container] (Next.js)  <──  [Cloudflare Tunnel]  <──  Your Phone (Anywhere)
```
