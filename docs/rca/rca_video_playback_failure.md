# Root Cause Analysis: Dashboard Video Playback Failures

**Date:** 2026-06-13
**Author:** Antigravity 
**Status:** Resolved
**Impact:** High (Users were entirely unable to review or play raw and processed videos within the Next.js dashboard).

---

## 1. Problem Description
The Next.js interactive Dashboard was completely failing to render video playback. The failure presented in two separate Dashboard components, seemingly related but stemming from two entirely distinct backend issues:
1. **Media Review Queue**: Videos failed to load, displaying a broken media player (HTTP 404).
2. **Processed Videos Showcase**: Finalized videos rendered a black screen and refused to buffer or play (CORS blockage).

---

## 2. Root Cause Analysis

### Issue A: Media Review Queue (`404 Not Found`)
The "Media Review Queue" relies on the `dashboard/src/app/api/video/route.js` endpoint to stream local video files to the browser without incurring cloud egress costs. 

* **The Mechanism**: The Next.js API parses the `gcs_uri` (e.g., `gs://bucket/reels/71d2cdda_reel.mp4`), extracts the filename, and searches for that exact filename in the local `data/downloads/` directory.
* **The Failure**: The `GCSUploaderService.upload_file` Python method was prepending a unique 8-character UUID to the filename right before pushing it to Google Cloud Storage (to prevent bucket collisions). **However, it never renamed the original local file.**
* **The Result**: The database recorded the `gcs_uri` as `71d2cdda_reel.mp4`, but the file on the local disk was still named `reel.mp4`. When Next.js tried to stream the file using the database record, it returned a `404 Not Found`.

### Issue B: Processed Videos Showcase (CORS Blockage)
The "Processed Videos Showcase" serves finalized videos directly from Firebase Storage using signed HTTP URLs.

* **The Mechanism**: The dashboard uses a standard HTML5 `<video src="https://storage.googleapis.com/..." preload="metadata" />` tag.
* **The Failure**: Video seeking and metadata preloading require browsers to make HTTP `Range` requests (e.g., `bytes=0-1000`). Google Cloud Storage buckets block cross-origin `Range` requests by default unless an explicit Cross-Origin Resource Sharing (CORS) policy is attached to the bucket.
* **The Result**: Safari and Chrome aborted the media requests at the network layer, preventing the videos from initializing or playing.

---

## 3. Resolution

Both issues were identified and patched immediately.

> [!TIP]
> **Resolution A (Path Reconciliation)**
> I modified `src/scraper/services/gcs_uploader_service.py`. The service now executes an `os.rename()` on the local file to exactly match the newly generated GCS UUID *prior* to upload. The local file cache now perfectly mirrors the remote bucket.

> [!TIP]
> **Resolution B (CORS Policy Injection)**
> I authored a `cors.json` payload allowing `GET`, `HEAD`, `OPTIONS` and whitelisting the `Range` and `Accept-Ranges` headers. I then executed `gcloud storage buckets update` to bind this policy directly to both the `raw-input` and `processed-output` buckets.

## 4. Preventative Measures
1. **Local vs Cloud State Synchronization**: For future pipeline enhancements, any mutator functions that alter cloud metadata (like generating UUIDs) must strictly enforce identical mutations on the local filesystem state.
2. **Infrastructure as Code (IaC)**: If we spin up new staging or production Firebase buckets, the CORS configuration step should be added to the setup scripts to prevent regressions on fresh deployments.
