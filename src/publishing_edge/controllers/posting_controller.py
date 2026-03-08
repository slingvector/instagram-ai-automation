import logging
import os
import tempfile
import time
from google.cloud import firestore, storage

from src.publishing_edge.services.adb_client import ADBClient
from src.publishing_edge.services.appium_posting_service import AppiumPostingService
from src.publishing_edge.services.warmup_service import WarmupService
from src.publishing_edge.config import (
    GCP_PROJECT_ID, GCS_PROCESSED_BUCKET,
    DEVICE_UDID, HUMAN_REVIEW_ENABLED
)

logger = logging.getLogger(__name__)

# How often to poll Firestore for human review approval (seconds)
REVIEW_POLL_INTERVAL = 10
# Max wait time for human to approve/reject (minutes)
REVIEW_TIMEOUT_MINUTES = int(os.getenv("REVIEW_TIMEOUT_MINUTES", "10"))


class PostingController:
    """
    Orchestrates the full Reel publishing flow:
      1. Download processed video from GCS to device
      2. Stage draft on Instagram (AppiumPostingService)
      3. Update Firestore status to 'awaiting_approval'
      4. Poll Firestore for human approval/rejection
      5. Execute Share or Cancel based on reviewer decision
      6. Update final Firestore status (posted / rejected / failed)

    Follows SRP — this class only orchestrates, it does not do low-level device work.
    """

    def __init__(self):
        self.db = firestore.Client(project=GCP_PROJECT_ID)
        self.gcs = storage.Client(project=GCP_PROJECT_ID)
        self.adb = ADBClient(device_udid=DEVICE_UDID)
        self.appium = AppiumPostingService()
        self.warmup = WarmupService()

    def execute(self, job_id: str) -> bool:
        """
        Main entry point. Fetches the job doc, runs the full posting pipeline.
        All Firestore status transitions happen here.
        Returns True if the post was successfully PUBLISHED, False otherwise.
        """
        job_ref = self.db.collection("job_queue").document(job_id)
        job = job_ref.get()

        if not job.exists:
            logger.error(f"Job {job_id} not found in Firestore.")
            return False

        data = job.to_dict()
        gcs_uri = data.get("gcs_processed_video_uri") or data.get("gcs_raw_video_uri")
        ai_meta = data.get("ai_metadata", {})
        caption = ai_meta.get("caption", "")
        hashtags = ai_meta.get("hashtags", [])
        full_caption = f"{caption}\n\n{' '.join(hashtags)}" if hashtags else caption
        
        # Audio muted flag set by the Downloader
        audio_muted = data.get("audio_muted", False)

        logger.info(f"[{job_id}] Starting posting pipeline. URI: {gcs_uri} | Muted: {audio_muted}")

        # ── Step 1: Lock job to prevent double processing ────────────────────
        job_ref.update({
            "status": "POSTING_IN_PROGRESS",
            "posting_started_at": firestore.SERVER_TIMESTAMP,
        })

        try:
            # ── Step 2: Download processed video from GCS to device ──────────
            device_video_path = self._download_to_device(gcs_uri, job_id)

            # ── Step 3: Warm up account organically before posting ────────────
            logger.info(f"[{job_id}] Initiating 1-minute organic warmup...")
            self.warmup.perform_warmup(duration_minutes=1)

            logger.info(f"[{job_id}] Force-stopping Instagram for clean posting state...")
            self.adb.stop_instagram()
            time.sleep(2)

            # ── Step 4: Stage on Instagram (no Share yet) ─────────────────────
            self.appium.prepare_reel_post(
                video_device_path=device_video_path,
                caption=full_caption,
                needs_audio=audio_muted
            )

            if HUMAN_REVIEW_ENABLED:
                # ── Step 4: Await human review ────────────────────────────────
                job_ref.update({
            "status": "AWAITING_HUMAN_APPROVAL",
            "review_prompt": "Reel draft is staged on device. Approve or reject in Firestore.",
            "awaiting_since": firestore.SERVER_TIMESTAMP,
        })
                logger.info(f"[{job_id}] Draft staged. Waiting for human approval in Firestore...")

                decision = self._wait_for_review_decision(job_ref)

                if decision == "APPROVED":
                    self.appium.share_post()
                    job_ref.update({
                        "status": "PUBLISHED",
                        "posted_at": firestore.SERVER_TIMESTAMP,
                    })
                    logger.info(f"[{job_id}] ✅ Posted to Instagram.")
                    return True

                elif decision == "REJECTED":
                    self.appium.cancel_post()
                    job_ref.update({
                        "status": "REJECTED_BY_REVIEWER",
                        "rejected_at": firestore.SERVER_TIMESTAMP,
                    })
                    logger.info(f"[{job_id}] ❌ Post rejected by reviewer.")
                    return False

                else:  # timeout
                    self.appium.cancel_post()
                    job_ref.update({
                        "status": "REVIEW_TIMEOUT",
                        "error": f"No review decision after {REVIEW_TIMEOUT_MINUTES} minutes.",
                    })
                    logger.warning(f"[{job_id}] Review timed out.")
                    return False

            else:
                # Auto-post mode (HUMAN_REVIEW_ENABLED=false)
                self.appium.share_post()
                job_ref.update({
                    "status": "PUBLISHED",
                    "posted_at": firestore.SERVER_TIMESTAMP,
                })
                logger.info(f"[{job_id}] ✅ Auto-posted to Instagram.")
                return True

        except Exception as e:
            logger.error(f"[{job_id}] Posting pipeline failed: {e}", exc_info=True)
            job_ref.update({
                "status": "FAILED",
                "error": str(e),
                "failed_at": firestore.SERVER_TIMESTAMP,
            })
            self.appium.end_session()
            return False

    # ── Private Helpers ────────────────────────────────────────────────────────

    def _download_to_device(self, gcs_uri: str, job_id: str) -> str:
        """
        Downloads the processed video from GCS to the local machine,
        then pushes it to the Android device via ADB.
        Returns the on-device path.
        """
        # Parse gs://bucket/path
        path_without_scheme = gcs_uri.replace("gs://", "")
        bucket_name, blob_path = path_without_scheme.split("/", 1)

        filename = f"mcr_{job_id}.mp4"
        local_path = os.path.join(tempfile.gettempdir(), filename)

        logger.info(f"Downloading {gcs_uri} → {local_path}")
        bucket = self.gcs.bucket(bucket_name)
        bucket.blob(blob_path).download_to_filename(local_path)

        logger.info(f"Pushing {filename} to device /sdcard/Download/")
        device_path = self.adb.push_file(local_path, "/sdcard/Download/")

        os.remove(local_path)  # clean up local temp file
        return device_path

    def _wait_for_review_decision(self, job_ref) -> str:
        """
        Polls Firestore every REVIEW_POLL_INTERVAL seconds until the reviewer
        sets status to 'APPROVED' or 'REJECTED', or until timeout.
        Returns 'APPROVED', 'REJECTED', or 'timeout'.
        """
        deadline = time.time() + (REVIEW_TIMEOUT_MINUTES * 60)
        while time.time() < deadline:
            snap = job_ref.get()
            status = snap.to_dict().get("status", "")
            if status == "APPROVED":
                return "APPROVED"
            if status == "REJECTED":
                return "REJECTED"
            logger.debug(f"Waiting for review... current status: {status}")
            time.sleep(REVIEW_POLL_INTERVAL)
        return "timeout"
