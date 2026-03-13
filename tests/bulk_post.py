"""
Bulk Poster State Machine: Ingest trending geopolitical videos and post them
to Instagram as Reels with a 5-minute gap between each post.

This script uses an SQLite-backed State Machine to resume
interrupted runs and prevent duplicate work on failures.
"""
import os, sys, time, logging, traceback, sqlite3, argparse
from typing import Dict, Any, List, Iterator, Optional
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

from src.ingestion.base import Platform
from src.ingestion.adapters.trending_adapter import TrendingAdapter
from src.ingestion.downloader import UniversalDownloader
from src.scraper.services.gcs_uploader_service import GCSUploaderService
from src.cloud_function.services.vertex_ai_service import VertexAIService
from src.cloud_function.services.ollama_service import OllamaService
from src.cloud_function.repositories.job_repository import JobRepository
from src.publishing_edge.controllers.posting_controller import PostingController
from src.publishing_edge.services.adb_client import ADBClient
from src.publishing_edge.config import DEVICE_UDID
from src.media_factory.services.video_processor_service import VideoProcessorService
from src.orchestration.state_manager import StateManager, ReelState
from src.utils.preflight import PreFlightDiagnostic
from src.utils.proxy_helper import ProxyHelper

TOTAL_REELS = 4
GAP_SECONDS = 90  # Reduced to 1.5 minutes for industrial scale

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "mcr-relay-1772228380")
BUCKET     = os.getenv("GCS_BUCKET_NAME", "mcr-relay-1772228380-raw-input")

# Extra SEO terms so we get a wide content pool (beyond what's in trending_sources.yaml)
# Professional-grade Balanced Global & Regional SEO Pool
EXTRA_SEARCH_TERMS = [
    # SPORTS (GLOBAL & REGIONAL)
    "Champions League 2026 highlights", "NBA top 10 plays today", "F1 race summary global",
    "UFC viral knockouts", "Premier League best goals 2026", "IPL 2026 amazing catches",
    "Cricket world cup classic moments", "Badminton smash compilation", "Volleyball spike highlights",
    # AI & TECH (GLOBAL & SILICON VALLEY)
    "NVIDIA AI summit 2026 highlights", "OpenAI Sora cinematic examples", "Silicon Valley tech news today",
    "Robotics breakthrough 2026", "ChatGPT-5 leaks and rumors", "Tesla AI Day 2026 recap",
    "Quantum computing explained 2026", "AI video generation workflow",
    # FINANCE (US & GLOBAL)
    "US Stock Market opening bell", "Federal Reserve interest rate update", "Global economy 2026 outlook",
    "Bitcoin price surge live", "Wall Street highlights today", "FinTech trends 2026 global",
    "Trading floor intense moments", "Economic news Bloomberg recap",
    # TRAVEL & LUXURY (INTERNATIONAL)
    "Best places to travel 2026 global", "Luxury destinations 2026 reveal", "Hidden gems travel reels",
    "Beautiful Destinations global tour", "National Geographic nature viral", "Paris Milan Fashion Week 2026",
    # BEAUTY & FASHION (GLOBAL)
    "Vogue makeup tutorial 2026", "High-end fashion trends 2026", "Street style global hubs",
    "Skincare breakthrough 2026", "Viral runway moments", "Milan fashion week highlights"
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


def random_jitter(min_s=5, max_s=15, label="Section Jitter"):
    """Inject human-like randomized delay to avoid bot detection patterns."""
    import random
    secs = random.uniform(min_s, max_s)
    logger.info(f"⏳ {label}: Waiting {secs:.2f}s jitter...")
    time.sleep(secs)


from pathlib import Path

class BulkPosterStateMachine:
    def __init__(self):
        self.proxy_helper = ProxyHelper()
        proxy_url = self.proxy_helper.get_proxy()
        
        self.state_manager = StateManager()
        self.downloader = UniversalDownloader(output_dir=Path("data/downloads"), proxy=proxy_url)
        self.uploader = GCSUploaderService(bucket_name=BUCKET, proxy=proxy_url)
        self.vertex_ai = VertexAIService(project_id=PROJECT_ID)
        self.local_ai = OllamaService(model="mistral")
        self.job_repo = JobRepository(project_id=PROJECT_ID)
        self.video_service = VideoProcessorService(project_id=PROJECT_ID)
        self.posting_controller = PostingController()

    def discover_new_content(self, needed_count: int, exclude_platforms: List[str] = None, min_views: int = None):
        """Fetch new content to fill the pipeline if needed."""
        logger.info(f"Ingesting trending content pool (expanded SEO terms)...")
        # Ensure we use a fresh adapter or update its config
        self.adapter = TrendingAdapter()
        
        # Merge extra terms into the adapter's config
        existing_terms = self.adapter.config.get("sources", {}).get("search_terms", [])
        all_terms = list(set(existing_terms + EXTRA_SEARCH_TERMS))
        self.adapter.config.setdefault("sources", {})["search_terms"] = all_terms
        logger.info(f"Using {len(all_terms)} SEO search terms for discovery.")

        added = 0
        try:
            # Now a generator for streaming
            pool = self.adapter.fetch(exclude_platforms=exclude_platforms, min_views=min_views)
            for item in pool:
                if added >= needed_count:
                    break
                # Immediate persistence
                if self.state_manager.add_discovered_reel(item.url, item.title, item.platform, item.niche):
                    title_preview = item.title[:50] if item.title else "No Title"
                    logger.info(f"New item SCANNED: {title_preview}... ({item.url})")
                    added += 1
                else:
                    logger.debug(f"Skipping already known item: {item.url}")
        except Exception as e:
            logger.error(f"Error during streaming discovery: {e}")
            traceback.print_exc()
            
        logger.info(f"Added {added} new high-engagement reels to the state tracked queue (SCANNED).")

    def process_queue(self, retry_failed: bool = False, exclude_platforms: List[str] = None, min_views: int = None):
        """Process all pending items in the state manager."""
        # 0. PRE-FLIGHT CHECKS (Hardened v2)
        logger.info("Running Pre-Flight Hardware & Software Diagnostics...")
        diagnostic = PreFlightDiagnostic()
        results = diagnostic.run_all()
        all_passed = True
        for check, (success, message) in results.items():
            if not success:
                logger.error(f"❌ PRE-FLIGHT FAILED [{check}]: {message}")
                all_passed = False
            else:
                logger.info(f"✅ {check}: {message}")
        
        if not all_passed:
            logger.critical("Aborting run due to pre-flight failures. Please check hardware/server connections.")
            return

        pending_reels = self.state_manager.get_pending_reels(include_failed=retry_failed)
        
        if not pending_reels:
            logger.info("No pending reels to process. We need to discover more.")
            self.discover_new_content(TOTAL_REELS, exclude_platforms=exclude_platforms, min_views=min_views)
            pending_reels = self.state_manager.get_pending_reels(include_failed=retry_failed)
            
        # Limit to TOTAL_REELS if we somehow have way too many
        pending_reels = pending_reels[:TOTAL_REELS]
        total = len(pending_reels)
        
        logger.info(f"Starting state machine processing for {total} reels.")
        
        results = {"success": 0, "failed": 0}

        for i, reel in enumerate(pending_reels, 1):
            tag = f"[{i}/{total}]"
            reel_title = reel.get('title') or "Untitled"
            logger.info(f"{tag} ── Processing reel: {reel_title}")
            
            try:
                wait_time = self._process_single_reel(reel, tag)
                if wait_time > 0:
                    results["success"] += 1
                    if i < total:
                        logger.info(f"⏳ Waiting {wait_time // 60} minutes ({wait_time}s) before next reel...")
                        time.sleep(wait_time)
            except Exception as e:
                logger.error(f"{tag} ❌ Fatal Failure for this reel: {e}")
                traceback.print_exc()
                self.state_manager.mark_failed(reel['url'], str(e))
                results["failed"] += 1

        logger.info(
            f"═══ Bulk Poster Complete ═══\n"
            f"  ✅ Posted/Success: {results['success']}\n"
            f"  ❌ Failed: {results['failed']}"
        )

    def _process_single_reel(self, reel: Dict[str, Any], tag: str) -> int:
        """
        Runs a reel through the state transitions until posted.
        Returns the gap wait time in seconds if a real post occurred,
        otherwise 0.
        """
        state = reel['state']
        url = reel['url']
        wait_time = 0

        # State 0: SCANNED -> DISCOVERED (AI Relevance Filtering)
        if state in [ReelState.SCANNED, ReelState.FAILED]:
            # Only do AI check if we don't have confirmation yet
            logger.info(f"{tag} Performing AI Relevance Check (Gemini)...")
            niche = reel.get('niche', 'geopolitics')
            title = reel.get('title', '')
            
            if self.vertex_ai.is_relevant_content(title, niche):
                logger.info(f"{tag} ✅ Content confirmed relevant.")
                self.state_manager.update_state(url, ReelState.DISCOVERED)
                state = ReelState.DISCOVERED
            else:
                logger.warning(f"{tag} ❌ Discarding semantically irrelevant content: {title}")
                self.state_manager.mark_failed(url, "IRRELEVANT_CONTENT")
                return 0 
        else:
            logger.info(f"{tag} Skipping AI relevance check: Already completed.")

        # State 1: DISCOVERED -> DOWNLOADED
        if state in [ReelState.DISCOVERED, ReelState.FAILED]:
            if not reel.get('gcs_uri'):
                random_jitter(label="Ingestion Prep")
                logger.info(f"{tag} Downloading & uploading to GCS...")
                try:
                    # Execute atomic download & upload
                    result = self.downloader.download(url, filename_hint=reel.get('title', 'reel'))
                    if result.success:
                        gcs_uri = self.uploader.upload_file(result.video_path)
                        self.state_manager.update_state(url, ReelState.DOWNLOADED, gcs_uri=gcs_uri)
                        reel['gcs_uri'] = gcs_uri
                        state = ReelState.DOWNLOADED
                    else:
                        raise RuntimeError(f"Download failed: {result.error}")
                except Exception as e:
                    logger.error(f"{tag} Ingestion failed for {url}: {e}")
                    self.state_manager.mark_failed(url, str(e))
                    return 0
            else:
                logger.info(f"{tag} Skipping Download: URI already exists.")
                state = ReelState.DOWNLOADED
        else:
            logger.info(f"{tag} Skipping Download: Already completed.")

        # State 2: DOWNLOADED -> CAPTIONED
        if state in [ReelState.DOWNLOADED, ReelState.FAILED]:
            if not reel.get('ai_metadata'):
                logger.info(f"{tag} Generating AI caption...")
                gcs_uri = reel['gcs_uri']
                # ... AI logic ...
                try:
                    metadata = self.vertex_ai.analyze_video(gcs_uri)
                except Exception as e:
                    logger.warning(f"{tag} Vertex AI failed: {e}. Falling back to local Ollama...")
                    metadata = self.local_ai.generate_copy_from_metadata(reel['title'], context=f"Source: {reel['source']}")
                
                self.state_manager.update_state(url, ReelState.CAPTIONED, ai_metadata=metadata)
                reel['ai_metadata'] = metadata
                state = ReelState.CAPTIONED
            else:
                logger.info(f"{tag} Skipping Captioning: Metadata already exists.")
                state = ReelState.CAPTIONED
        else:
            logger.info(f"{tag} Skipping Captioning: Already completed.")

        # State 3: CAPTIONED -> JOB_CREATED
        if state in [ReelState.CAPTIONED, ReelState.FAILED]:
            if not reel.get('job_id'):
                logger.info(f"{tag} Creating Firestore job...")
                job_id = self.job_repo.create_job(reel['gcs_uri'], reel['ai_metadata'])
                self.state_manager.update_state(url, ReelState.JOB_CREATED, job_id=job_id)
                reel['job_id'] = job_id
                state = ReelState.JOB_CREATED
            else:
                logger.info(f"{tag} Skipping Job Creation: Job ID already exists.")
                state = ReelState.JOB_CREATED
        else:
            logger.info(f"{tag} Skipping Job Creation: Already completed.")

        # State 4: JOB_CREATED -> MEDIA_PROCESSED
        if state in [ReelState.JOB_CREATED, ReelState.FAILED]:
            if not reel.get('processed_uri'):
                logger.info(f"{tag} Running Media Factory...")
                job_id = reel['job_id']
                gcs_uri = reel['gcs_uri']
                metadata = reel['ai_metadata']
                burn_in_text = metadata.get("burn_in_text", "")
                caption_text = metadata.get("caption", "")
                niche = reel.get('niche', 'general')
                processed_uri, tx_receipt = self.video_service.apply_burn_in(gcs_uri, burn_in_text, caption_text, job_id, niche=niche)
                
                # CRITICAL: Sync the processed video URI to Firestore so the posting controller sees it
                self.job_repo.update_job(job_id, {
                    "gcs_processed_video_uri": processed_uri,
                    "digital_passport_tx_hash": tx_receipt,
                    "status": "READY_FOR_POSTING"
                })

                self.state_manager.update_state(url, ReelState.MEDIA_PROCESSED, processed_uri=processed_uri, tx_hash=tx_receipt)
                reel['processed_uri'] = processed_uri
                reel['tx_hash'] = tx_receipt
                state = ReelState.MEDIA_PROCESSED
            else:
                logger.info(f"{tag} Skipping Media Factory: Processed URI exists.")
                state = ReelState.MEDIA_PROCESSED
        else:
            logger.info(f"{tag} Skipping Media Factory: Already completed.")

        # State 5: MEDIA_PROCESSED -> POSTED
        if state == ReelState.MEDIA_PROCESSED:
            logger.info(f"{tag} Force-stopping Instagram for clean state...")
            try:
                ADBClient(DEVICE_UDID).stop_instagram()
                time.sleep(2)
            except Exception as e:
                logger.warning(f"Could not stop instagram: {e}")

            job_id = reel['job_id']
            try:
                random_jitter(label="Posting Buffer")
                success = self.posting_controller.execute(job_id)
                
                if success:
                    logger.info(f"{tag} ✅ Reel posted to Instagram!")
                    self.state_manager.update_state(url, ReelState.POSTED)
                    # Calculate dynamic wait based on gap
                    wait_time = GAP_SECONDS
                else:
                    logger.warning(f"{tag} ❌ Reel post failed. Marking as failed in state manager.")
                    self.state_manager.mark_failed(url, "PostingController pipeline failed.")
                    wait_time = 15
            except Exception as e:
                logger.error(f"{tag} ❌ Unexpected pipeline error: {e}")
                self.state_manager.mark_failed(url, f"Pipeline Exception: {str(e)}")
                wait_time = 15
        
        return wait_time


def run():
    global TOTAL_REELS, GAP_SECONDS
    
    parser = argparse.ArgumentParser(description="Bulk Poster State Machine for Instagram Reels.")
    parser.add_argument("--count", type=int, default=TOTAL_REELS, help="Total reels to process")
    parser.add_argument("--gap", type=int, default=GAP_SECONDS, help="Wait time in seconds between posts")
    parser.add_argument("--retry-failed", action="store_true", help="Retry items in FAILED state")
    parser.add_argument("--no-youtube", action="store_true", help="Disable YouTube discovery")
    parser.add_argument("--min-views", type=int, help="Minimum views for discovery")
    parser.add_argument("--clear-dedup-discovery", action="store_true", help="Clear the discovery dedup database")
    args = parser.parse_args()
    TOTAL_REELS = args.count
    GAP_SECONDS = args.gap

    logger.info(f"═══ Bulk Poster State Machine: {TOTAL_REELS} reels, {GAP_SECONDS//60}min gap ═══")
    
    if args.clear_dedup_discovery:
        db_path = os.path.join("data", "content_dedup.db")
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM seen_dm_ids")
                conn.commit()
                logger.info("Discovery dedup cache cleared.")
            except Exception as e:
                logger.warning(f"Could not clear discovery cache: {e}")
            finally:
                conn.close()

    sm = BulkPosterStateMachine()
    
    # We can pass these from config or CLI if we want, for now, let's just let it run
    exclude_platforms = [Platform.YOUTUBE] if args.no_youtube else []
    sm.process_queue(
        retry_failed=args.retry_failed, 
        exclude_platforms=exclude_platforms, 
        min_views=args.min_views
    )


if __name__ == "__main__":
    run()
