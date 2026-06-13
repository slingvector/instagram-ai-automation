"""
Bulk DM Poster: Ingest Reels from Instagram DMs and post them
to the main account with a 5-minute gap between each post.
"""
import os, sys, time, logging, traceback
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
try:
    from src.utils.gcp_logging import setup_cloud_logging
    setup_cloud_logging()
except ImportError:
    pass

logger = logging.getLogger("bulk_dm_poster")

from src.ingestion.adapters.dm_adapter import DMAdapter
from src.scraper.services.gcs_uploader_service import GCSUploaderService
from src.cloud_function.services.vertex_ai_service import VertexAIService
from src.cloud_function.repositories.job_repository import JobRepository
from src.publishing_edge.controllers.posting_controller import PostingController
from src.publishing_edge.services.adb_client import ADBClient
from src.publishing_edge.config import DEVICE_UDID

GAP_SECONDS = 3 * 60  # 3 minutes
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "mcr-relay-1772228380")
BUCKET     = os.getenv("GCS_BUCKET_NAME", "mcr-relay-1772228380-raw-input")

def post_single_reel(item, index, total):
    """Process and post a single reel sourced from DM. Returns (success_bool, wait_time_seconds)."""
    tag = f"[{index}/{total}]"
    logger.info(f"{tag} ── Processing DM Reel: {item.url}")

    # 1. Download & Upload to GCS
    logger.info(f"{tag} Downloading & uploading to GCS...")
    uploader = GCSUploaderService(bucket_name=BUCKET)
    gcs_uri, duration = uploader.download_and_upload(item.url)
    logger.info(f"{tag} GCS: {gcs_uri} (Duration: {duration}s)")

    # Calculate dynamic wait: 1.25x duration (min 180s, max 600s)
    dynamic_gap = max(180, min(600, int(duration * 1.25)))

    # 2. Vertex AI caption
    logger.info(f"{tag} Generating AI caption...")
    ai = VertexAIService(project_id=PROJECT_ID)
    try:
        metadata = ai.analyze_video(gcs_uri)
    except Exception as e:
        logger.warning(f"{tag} Vertex AI analysis failed, using fallback metadata: {e}")
        metadata = {
            "caption": "Check out this amazing find! 🔍 #reels #viral",
            "hashtags": ["reels", "trending", "content"]
        }
    
    caption = metadata.get("caption", "")
    logger.info(f"{tag} Caption: {caption[:80]}...")

    # 3. Firestore job
    logger.info(f"{tag} Creating Firestore job...")
    repo = JobRepository(project_id=PROJECT_ID)
    job_id = repo.create_job(gcs_uri, metadata)
    repo.db.collection("job_queue").document(job_id).update({
        "status": "READY_FOR_PUBLISHING"
    })
    logger.info(f"{tag} Job {job_id} → READY_FOR_PUBLISHING")

    # 4. Appium auto-post
    logger.info(f"{tag} Force-stopping Instagram for clean state...")
    ADBClient(DEVICE_UDID).stop_instagram()
    time.sleep(2)

    controller = PostingController()
    success = controller.execute(job_id)
    
    if success:
        # 5. Register in Dedup ONLY on success
        from src.ingestion.dedup import ContentDedup
        dedup = ContentDedup()
        msg_id = item.raw_metadata.get("message_id")
        thread_url = item.raw_metadata.get("thread_url")
        if msg_id and thread_url:
            dedup.register_dm(msg_id, thread_url, item.url)
            
        logger.info(f"{tag} ✅ Reel posted successfully and marked as seen!")
    else:
        logger.warning(f"{tag} ❌ Reel post failed. Not marking as seen.")
        
    return success, dynamic_gap

def run():
    logger.info(f"═══ Bulk DM Poster ═══")
    
    # Check credentials
    if not os.getenv("IG_READONLY_USERNAME") or not os.getenv("IG_READONLY_PASSWORD"):
        logger.error("IG_READONLY_USERNAME or IG_READONLY_PASSWORD not set in .env")
        return

    # Ingest from DMs
    logger.info("Scraping DMs for Reel URLs...")
    is_headless = os.getenv("HEADLESS", "True").lower() == "true"
    adapter = DMAdapter(headless=is_headless)
    to_post = adapter.fetch()

    if not to_post:
        logger.info("No new Reel DMs found. Exiting.")
        return

    # User requested initial test of exactly 2 posts!
    to_post = to_post[:2]
    logger.info(f"Found and limiting to {len(to_post)} new Reels to post for this test.")

    results = {"success": 0, "failed": 0}

    for i, item in enumerate(to_post, 1):
        wait_sec = GAP_SECONDS # Fallback
        try:
            ok, wait_sec = post_single_reel(item, i, len(to_post))
            if ok:
                results["success"] += 1
        except Exception as e:
            logger.error(f"[{i}/{len(to_post)}] ❌ Failed: {e}")
            traceback.print_exc()
            results["failed"] += 1
            # Fatal error (e.g. yt-dlp failed download). Skip the long wait.
            wait_sec = 15

        # Wait between posts (skip wait after the last one)
        if i < len(to_post):
            logger.info(
                f"⏳ Waiting {wait_sec // 60} minutes ({wait_sec}s) before next post... "
                f"({results['success']} posted, {results['failed']} failed)"
            )
            time.sleep(wait_sec)

    logger.info(
        f"═══ Bulk DM Poster Complete ═══\n"
        f"  ✅ Posted: {results['success']}\n"
        f"  ❌ Failed: {results['failed']}"
    )

if __name__ == "__main__":
    run()
