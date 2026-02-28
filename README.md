# instagram-ai-automation

> **ModernOS Content Relay (MCR)** — A fully automated Instagram Reel posting pipeline powered by Appium, ADB, and Gemini AI.

## What It Does

1. **Scrapes** a source Instagram Reel URL
2. **Downloads & processes** the video (via cloud media factory)
3. **Pushes** the video to an Android device
4. **Automates** the entire Instagram posting flow (gallery → editor → caption → Share) using Appium + ADB
5. **Stages a draft** and waits for human approval in Firestore before posting live

---

## Architecture

```
[Reel URL]
    │
    ▼
src/scraper/              ← Scrape reel metadata + download video
    │
    ▼
src/media_factory/        ← Process, resize, watermark video
    │
    ▼
src/cloud_function/       ← GCP Cloud Function: trigger + orchestrate
    │
    ▼
src/publishing_edge/      ← Android device automation (Appium + ADB)
    ├── controllers/      ← PostingController: orchestrates the pipeline
    └── services/
        ├── appium_posting_service.py  ← Full Instagram UI automation
        └── adb_client.py              ← ADB helper (tap, screenshot, push)
    │
    ▼
[Firestore APPROVED]
    │
    ▼
share_post()              ← Taps Share → Reel goes live
```

---

## Tools

### `tools/record_flow.py` — Flow Recorder
Records a screen video + XML UI snapshots while you manually perform any Instagram flow.  
Used to teach the automation new flows and debug coordinate issues.

```bash
python tools/record_flow.py create_reel
# Open Instagram, do the flow, close app → session saved in recordings/
```

### `tools/analyze_flow.py` — AI Flow Analyzer
Reads a recorded session, detects screen transitions from XML diffs, and uses Gemini AI
to generate Python automation step stubs.

```bash
python tools/analyze_flow.py recordings/create_reel_20260228_192731
```

---

## Setup

### Prerequisites
- Python 3.11+
- Android device with USB debugging enabled
- Appium v3.x + UiAutomator2 driver
- GCP project with Firestore + Cloud Storage

### Install

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `DEVICE_UDID` | ADB device serial (`adb devices`) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP service account JSON |
| `FIRESTORE_PROJECT_ID` | Your GCP project ID |
| `GCS_BUCKET_PROCESSED` | GCS bucket for processed videos |

### Start Appium

```bash
export ANDROID_HOME=/opt/homebrew
appium
```

### Run a Test Post

```bash
python test_post_bg.py
```

---

## How the XML-Based UI Automation Works

Rather than hardcoding pixel coordinates, every interaction uses a **3-strategy approach**:

1. **Appium element find** (by XPath / AccessibilityId)
2. **XML page_source scan** — dump the live UI tree, find elements by `text` / `content-desc` / `resource-id`
3. **ADB tap at known coords** — confirmed from real device XML recordings

### `tools/record_flow.py` was key
The recorder revealed the **exact element tree** on a 1440×3120 Samsung device:
- `"Video thumbnail"` in `content-desc` → identifies the correct gallery item
- `"Next"` at `(1237, 2969)` — bottom-right corner, not top-right
- `AutoCompleteTextView` at `(720, 1674)` — the caption field

---

## Debug Screenshots

Every pipeline run saves per-step screenshots + XML dumps to `debug/`:

```
debug/
  191229_01_instagram_launched.png
  191250_02_after_create_tap.png
  191257_03_after_reel_select.png
  191308_04_after_video_select.png
  191350_05_after_next.png
  195827_06_caption_entered.png
```

---

## Roadmap

- [ ] Full URL-to-post pipeline (Reel URL → download → process → post)
- [ ] Android Media Scanner trigger after video push
- [ ] `share_post()` validation + capture post URL
- [ ] Multi-account support
- [ ] Self-healing via XML cache + Gemini Vision fallback
