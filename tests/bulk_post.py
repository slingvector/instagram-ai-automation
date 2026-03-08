"""
Bulk Poster: Ingest trending geopolitical videos and post them
to Instagram as Reels with a 5-minute gap between each post.

This script resets the dedup cache for YouTube SEO hits before running
to ensure fresh content is discovered on every batch run.
"""
import os, sys, time, logging, traceback, sqlite3
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

logger = logging.getLogger("bulk_poster")

from src.ingestion.adapters.trending_adapter import TrendingAdapter
from src.scraper.services.gcs_uploader_service import GCSUploaderService
from src.cloud_function.services.vertex_ai_service import VertexAIService
from src.cloud_function.services.ollama_service import OllamaService
from src.cloud_function.repositories.job_repository import JobRepository
from src.publishing_edge.controllers.posting_controller import PostingController
from src.publishing_edge.services.adb_client import ADBClient
from src.publishing_edge.config import DEVICE_UDID

TOTAL_REELS = 10
GAP_SECONDS = 3 * 60  # 3 minutes

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "mcr-relay-1772228380")
BUCKET     = os.getenv("GCS_BUCKET_NAME", "mcr-relay-1772228380-raw-input")

# Extra SEO terms so we get a wide content pool (beyond what's in trending_sources.yaml)
EXTRA_SEARCH_TERMS = [
    "russia ukraine war update",
    "china taiwan strait tensions",
    "nuclear weapons explained",
    "cold war history documentary",
    "military technology 2025",
    "nato vs russia",
    "israel gaza explained",
    "world war 3 scenario",
    "oil crisis middle east",
    "drone warfare modern",
    "us navy south china sea",
    "arab spring documentary",
    "india pakistan border",
    "african proxy wars",
    "cyber warfare explained",
]


def clear_youtube_dedup():
    """Remove previously seen YouTube SEO entries from the dedup database
    so this batch run discovers fresh content."""
    db_path = os.path.join("data", "content_dedup.db")
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        deleted = cursor.execute(
            "DELETE FROM seen_dm_ids WHERE message_id LIKE 'yt_seo::%'"
        ).rowcount
        conn.commit()
        logger.info(f"Cleared {deleted} YouTube SEO entries from dedup cache.")
    except Exception as e:
        logger.warning(f"Could not clear dedup cache: {e}")
    finally:
        conn.close()


def post_single_reel(item, index, total):
    """Process and post a single reel. Returns (success_bool, wait_time_seconds)."""
    tag = f"[{index}/{total}]"
    logger.info(f"{tag} ── Starting: {item.title} ({item.url})")

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
        logger.warning(f"{tag} Vertex AI failed (maybe 429 quota?): {e}. Falling back to local Ollama text-only inference...")
        local_ai = OllamaService(model="mistral") # Ensure you run `ollama pull mistral` beforehand
        try:
            metadata = local_ai.generate_copy_from_metadata(item.title, context=f"Source: {item.source}")
        except Exception as ollama_err:
            logger.error(f"{tag} Local AI fallback also failed: {ollama_err}")
            metadata = {
                "caption": f"Must watch: {item.title}! 🔥 #trending #reels",
                "hashtags": ["trending", "reels", "viral", "foryou", item.source.lower()],
                "burn_in_text": "Watch this till the end!"
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
        # Note: Trending items are already registered in dedup during the fetch phase 
        # (in trending_adapter.py) to prevent massive memory duplicates. 
        # For bulk_post, since we fetch 50+ items and only post 10, the "prefetch dedup" 
        # is necessary to avoid showing the same top 10 next time. 
        # We'll leave the trending_adapter dedup logic alone for now to keep the pool fresh.
        logger.info(f"{tag} ✅ Reel posted to Instagram!")
    else:
        logger.warning(f"{tag} ❌ Reel post failed.")
        
    return success, dynamic_gap


def run():
    logger.info(f"═══ Bulk Poster: {TOTAL_REELS} reels, {GAP_SECONDS//60}min gap ═══")

    # Reset dedup so we get fresh YouTube SEO results
    clear_youtube_dedup()

    # Temporarily inject extra search terms into the config
    logger.info("Ingesting trending content pool (expanded SEO terms)...")
    adapter = TrendingAdapter()
    
    # Merge extra terms into the adapter's config
    existing_terms = adapter.config.get("sources", {}).get("search_terms", [])
    all_terms = list(set(existing_terms + EXTRA_SEARCH_TERMS))
    adapter.config.setdefault("sources", {})["search_terms"] = all_terms
    logger.info(f"Using {len(all_terms)} SEO search terms for discovery.")

    pool = adapter.fetch()

    if not pool:
        logger.error("No items found after expanded search. Aborting.")
        return

    logger.info(f"Content pool: {len(pool)} videos discovered.")

    # Sort by engagement (highest first) and take top N
    pool.sort(key=lambda x: x.engagement_score, reverse=True)
    to_post = pool[:TOTAL_REELS]

    logger.info(f"Selected top {len(to_post)} videos for posting:")
    for i, item in enumerate(to_post, 1):
        logger.info(f"  {i}. {item.title} ({item.view_count:,} views)")

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
        f"═══ Bulk Poster Complete ═══\n"
        f"  ✅ Posted: {results['success']}\n"
        f"  ❌ Failed: {results['failed']}"
    )


if __name__ == "__main__":
    run()
