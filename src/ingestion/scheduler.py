"""
src/ingestion/scheduler.py

APScheduler-based runner that polls all source adapters on their own schedule
and feeds qualifying ContentItems into the downstream processing pipeline.

Downstream: Each new ContentItem → UniversalDownloader → Firestore job → Appium posts it.

Run:
    python -m src.ingestion.scheduler
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.ingestion.adapters import DMAdapter, CreatorAdapter, CrossPlatformAdapter, TrendingAdapter
from src.ingestion.base import ContentItem, AccountProfile
from src.ingestion.downloader import UniversalDownloader
from src.ingestion.dedup import ContentDedup

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

_DOWNLOAD_DIR = Path("data/downloads")
_PROCESSED_BUCKET = os.environ.get("GCS_BUCKET_PROCESSED", "")


def _process_items(items: List[ContentItem], label: str):
    """
    Download each ContentItem, run visual dedup, then create a Firestore job
    to trigger the existing Media Factory → Appium pipeline.
    """
    if not items:
        logger.info(f"[{label}] No new items")
        return

    logger.info(f"[{label}] Processing {len(items)} new items")
    downloader = UniversalDownloader(output_dir=_DOWNLOAD_DIR)
    dedup = ContentDedup()

    for item in items:
        try:
            # Metadata pre-check (for freshly discovered URLs not yet downloaded)
            meta = downloader.prefetch_metadata(item.url)
            if meta:
                item.view_count  = item.view_count  or meta.get("view_count", 0)
                item.like_count  = item.like_count  or meta.get("like_count", 0)
                item.duration_seconds = item.duration_seconds or meta.get("duration")
                item.compute_engagement_score()

            # Download
            result = downloader.download(item.url, filename_hint=item.shortcode or "")
            if not result.success:
                logger.warning(f"Download failed for {item.url}: {result.error}")
                continue

            # Visual dedup after download
            if dedup.is_visual_duplicate(result.video_path):
                logger.info(f"Visual duplicate skipped: {item.url}")
                result.video_path.unlink(missing_ok=True)
                continue

            dedup.register_visual(result.video_path, item.dedup_key)

            # Flag audio status (IG will need to handle muted audio via Appium)
            if result.audio_muted:
                item.keep_audio = False
                logger.info(f"Audio muted by source for {item.url} — will use IG trending audio")

            # Create Firestore job via existing pipeline
            _create_firestore_job(item, result.video_path)

        except Exception as e:
            logger.error(f"Processing error for {item.url}: {e}")


def _create_firestore_job(item: ContentItem, video_path: Path):
    """
    Upload video to GCS and create a Firestore job document.
    This triggers the existing Media Factory → Appium pipeline.
    """
    try:
        from google.cloud import storage, firestore
        import uuid, datetime

        job_id = str(uuid.uuid4())
        gcs_path = f"raw/{item.source_type}/{job_id}_{video_path.name}"

        # Upload to GCS
        client = storage.Client()
        bucket = client.bucket(_PROCESSED_BUCKET)
        blob = bucket.blob(gcs_path)
        blob.upload_from_filename(str(video_path))
        gcs_uri = f"gs://{_PROCESSED_BUCKET}/{gcs_path}"

        # Create Firestore job
        db = firestore.Client()
        db.collection("posting_jobs").document(job_id).set({
            "job_id":         job_id,
            "status":         "pending",
            "gcs_uri":        gcs_uri,
            "platform":       item.platform,
            "source_type":    item.source_type,
            "niche":          item.niche,
            "target_account": item.target_account,
            "keep_audio":     item.keep_audio,
            "engagement_score": item.engagement_score,
            "created_at":     datetime.datetime.utcnow(),
        })

        logger.info(f"Firestore job created: {job_id} → {gcs_uri} [{item.target_account}]")

        # Clean up local file after GCS upload
        video_path.unlink(missing_ok=True)

    except Exception as e:
        logger.error(f"Firestore job creation failed: {e}")


# ── Adapter jobs ──────────────────────────────────────────────────────────────

def run_dm():
    logger.info("=== DMAdapter run ===")
    _process_items(DMAdapter().run(), "DM")

def run_creator():
    logger.info("=== CreatorAdapter run ===")
    _process_items(CreatorAdapter().run(), "Creator")

def run_cross_platform():
    logger.info("=== CrossPlatformAdapter run ===")
    _process_items(CrossPlatformAdapter().run(), "CrossPlatform")

def run_trending():
    logger.info("=== TrendingAdapter run ===")
    _process_items(TrendingAdapter().run(), "Trending")


# ── Scheduler entry point ─────────────────────────────────────────────────────

def main():
    scheduler = BlockingScheduler(timezone="UTC")

    # UC1: DMs — every 20 minutes
    scheduler.add_job(run_dm,             IntervalTrigger(minutes=20),  id="dm",             name="DM Scraper")

    # UC2: Creator watchlist — every 6 hours
    scheduler.add_job(run_creator,        IntervalTrigger(hours=6),     id="creator",        name="Creator Watchlist")

    # UC4: Cross-platform — every 3 hours
    scheduler.add_job(run_cross_platform, IntervalTrigger(hours=3),     id="cross_platform", name="Cross-Platform")

    # UC3: Trending — every 10 minutes
    scheduler.add_job(run_trending,       IntervalTrigger(minutes=10),  id="trending",       name="Trending Monitor")

    logger.info("MCR Ingestion Scheduler started.")
    logger.info("  UC1 DM:           every 20 min")
    logger.info("  UC2 Creator:      every 6h")
    logger.info("  UC3 Trending:     every 10 min")
    logger.info("  UC4 CrossPlatform:every 3h")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
