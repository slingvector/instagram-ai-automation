# instagram-ai-automation (Google Drive Flow)

> **ModernOS Content Relay (MCR)** — An automated Instagram Reel ingestion and processing pipeline.

## What It Does

1. **Scrapes** a source Instagram Reel or YouTube Video URL (trending adapters).
2. **Downloads & processes** the video (via local or cloud media factory).
3. **Generates AI copy** for the caption and hashtags.
4. **Pushes** the finalized video and metadata to a Google Drive folder for manual review and posting.

---

## Architecture

```
[Reel URL / Keyword]
    │
    ▼
src/scraper/              ← Scrape metadata + download video
    │
    ▼
src/media_factory/        ← Process, resize, watermark video
    │
    ▼
src/cloud_function/       ← Vertex AI copy generation
    │
    ▼
src/orchestration/        ← SQLite State Machine (State tracking)
    │
    ▼
[Google Drive Folder]     ← Final staging area
```

---

## Setup

### Prerequisites
- Python 3.11+
- GCP project with Firestore + Cloud Storage + Vertex AI

### Install

The project is installable as a Python package via `pyproject.toml`:

```bash
python -m venv venv && source venv/bin/activate
pip install -e .
```

### Download Binary Assets

```bash
# Download required emoji fonts
./scripts/setup_fonts.sh
```

### Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP service account JSON |
| `GCP_PROJECT_ID` | Your GCP project ID |
| `GCS_BUCKET_NAME` | GCS bucket for raw input |
| `GCS_PROCESSED_BUCKET` | GCS bucket for processed videos |

---

## Running the Pipeline

You can run the full discovery and processing pipeline using the `bulk_post.py` script:

```bash
python scripts/bulk_post.py --count 10 --gap 0
```
