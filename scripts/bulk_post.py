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

from src.media_factory.services.video_processor_service import VideoProcessorService
from src.orchestration.state_manager import StateManager, ReelState
from src.utils.preflight import PreFlightDiagnostic
from src.utils.proxy_helper import ProxyHelper
from src.utils.google_drive_service import GoogleDriveService

TOTAL_REELS = 25
GAP_SECONDS = 300  # 5 minute gap for 25-reel batch

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "mcr-relay-1772228380")
BUCKET     = os.getenv("GCS_BUCKET_NAME", "mcr-relay-1772228380-raw-input")


def clear_youtube_dedup():
    """Remove previously seen YouTube SEO entries from the dedup database
    so this batch run discovers fresh content."""
    db_path = os.path.join("data", "dedup.db")
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

PID_FILE = "/tmp/bulk_post.pid"
_lock_file = None

def acquire_lock():
    """Atomic PID lock to prevent multiple instances from running concurrently."""
    import fcntl
    global _lock_file
    try:
        # Use an open file handle that lives for the duration of the process
        _lock_file = open(PID_FILE, "w")
        # Attempt an exclusive, non-blocking lock
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file.write(str(os.getpid()))
        _lock_file.flush()
    except (IOError, OSError):
        try:
            with open(PID_FILE, "r") as f:
                pid = f.read().strip()
            logger.error(f"❌ Another instance is already running (PID: {pid}). Aborting.")
        except:
            logger.error("❌ Another instance is already running. Aborting.")
        sys.exit(1)

def release_lock():
    """Release the PID lock."""
    global _lock_file
    try:
        if _lock_file:
            import fcntl
            fcntl.flock(_lock_file, fcntl.LOCK_UN)
            _lock_file.close()
            _lock_file = None
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except:
        pass

class BulkPosterStateMachine:
    def __init__(self, manifest_path: str = "config/discovery_manifest.yaml", db_path: str = None):
        self.manifest_path = manifest_path
        self.db_path = db_path
        self.proxy_helper = ProxyHelper()
        proxy_url = self.proxy_helper.get_proxy()
        
        # Read download strategy from manifest
        from src.ingestion.services.discovery_service import DiscoveryService
        from src.ingestion.base import Platform
        discovery_service = DiscoveryService(self.manifest_path)
        tiktok_policy = discovery_service.get_downloader_policy(Platform.TIKTOK)
        
        if self.db_path:
             self.state_manager = StateManager(db_path=self.db_path)
        else:
             self.state_manager = StateManager()
        self.downloader = UniversalDownloader(
            output_dir=Path("data/downloads"), 
            proxy=proxy_url,
            tiktok_policy=tiktok_policy
        )
        self.uploader = GCSUploaderService(bucket_name=BUCKET, proxy=proxy_url)
        self.vertex_ai = VertexAIService(project_id=PROJECT_ID)
        self.local_ai = OllamaService(model="llama3.2")
        self.job_repo = JobRepository(project_id=PROJECT_ID)
        self.video_service = VideoProcessorService(project_id=PROJECT_ID)
        
        from src.utils.localsend_service import LocalSendService
        from src.utils.transcoder_service import HlsTranscoderService
        from src.utils.firebase_relay_service import FirebaseRelayService
        from dotenv import load_dotenv
        import os
        load_dotenv(override=True)
        
        self.localsend_service = LocalSendService(
            target_ip=os.getenv("LOCALSEND_TARGET_IP"),
            target_alias=os.getenv("LOCALSEND_ALIAS", "Galaxy S25")
        )
        self.hls_service = HlsTranscoderService(
            project_id=PROJECT_ID,
            cdn_host=os.getenv("RELAY_CDN_HOST")
        )
        self.firebase_service = FirebaseRelayService(
            bucket_name=os.getenv("FIREBASE_BUCKET", "mcr-relay-1781190111.appspot.com")
        )

    def discover_new_content(self, needed_count: int, exclude_platforms: List[str] = None, min_views: int = None):
        """Fetch new content AGGRESSIVELY using Broad Harvest mode."""
        logger.info(f"Broad Harvest: Populating pipeline with {needed_count} resources...")
        self.adapter = TrendingAdapter(manifest_path=self.manifest_path)

        added = 0
        try:
            # Stage 1: Broad Harvest (Raw URLs)
            pool = self.adapter.fetch_broad(exclude_platforms=exclude_platforms, min_views=min_views)
            for item in pool:
                if added >= needed_count:
                    break
                # Immediate persistence as SCANNED
                if self.state_manager.add_discovered_reel(item.url, item.title, item.platform, "broad_harvest", item.niche):
                    logger.info(f"Harvested: {item.url} (Added {added+1}/{needed_count})")
                    added += 1
                else:
                    logger.debug(f"Skipping known item: {item.url}")
        except Exception as e:
            logger.error(f"Broad harvest failed: {e}")
            
        logger.info(f"Broad Harvest Complete: Added {added} SCANNED items to the queue.")

    def process_queue(self, retry_failed: bool = False, exclude_platforms: List[str] = None, min_views: int = None, args=None):
        """Process all pending items in the state manager."""
        # 0. PRE-FLIGHT CHECKS (Hardened v2)
        logger.info("Running Pre-Flight Hardware & Software Diagnostics...")
    # 0. Pre-flight Checks
        if not args.skip_preflight:
            diagnostic = PreFlightDiagnostic()
            results = diagnostic.run_all()
            
            failed = False
            for name, (success, message) in results.items():
                level = logging.INFO if success else logging.ERROR
                logger.log(level, f"{'✅' if success else '❌'} {name}: {message}")
                if not success and name in ["ADB", "Appium", "Dependencies"]:
                    failed = True
            
            if failed:
                logger.critical("Aborting run due to pre-flight failures. Please check hardware/server connections.")
                sys.exit(1)
        else:
            logger.warning("⚠️ Skipping pre-flight checks as requested.")

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
                did_sync, wait_time = self._process_single_reel(reel, tag, args=args)
                if did_sync:
                    results["success"] += 1
                    if i < total and wait_time > 0:
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
        release_lock()

    def _process_single_reel(self, reel: Dict[str, Any], tag: str, args=None) -> tuple[bool, int]:
        """
        Runs a reel through the state transitions until posted.
        Returns (did_sync_new_reel, gap_wait_time_in_seconds).
        """
        url = reel['url']
        try:
            state = reel['state']
            wait_time = 0

            # State 0: SCANNED -> DISCOVERED (Intelligence Gate)
            if state in [ReelState.SCANNED, ReelState.FAILED]:
                logger.info(f"{tag} 🛡️ Intelligence Gate: Fetching engagement metrics for {url}...")
                
                # 1. Fetch deep metadata
                meta = self.downloader.prefetch_metadata(url)
                if not meta:
                    logger.warning(f"{tag} ❌ Could not fetch metadata. Marking as failed.")
                    self.state_manager.mark_failed(url, "METADATA_FETCH_FAILED")
                    return False, 0

                # 2. Calculate Engagement Rates
                from src.ingestion.services.discovery_service import DiscoveryService
                discovery_service = DiscoveryService(self.manifest_path)
                rates = discovery_service.calculate_rates(
                    meta["view_count"], meta["like_count"], meta["comment_count"]
                )
                
                # 3. Apply Thresholds (Hardened v3)
                platform = reel.get('platform') or 'instagram'
                p_filters = discovery_service.get_global_filters(platform)
                min_like_rate = p_filters.get("min_like_rate", 0.02)
                min_comment_rate = p_filters.get("min_comment_rate", 0.003)
                
                # High Volume Bypass: If views > 1M, we accept even if engagement is partially obscured
                if meta["view_count"] >= 1_000_000:
                    logger.info(f"{tag} ✅ Passed Intelligence Gate (High Volume Bypass: {meta['view_count']} views). Proceeding to DISCOVERED.")
                elif rates["like_rate"] < min_like_rate:
                    logger.warning(f"{tag} ❌ Rejected by Intelligence Gate: Like {rates['like_rate']:.3f} < {min_like_rate}")
                    self.state_manager.mark_failed(url, f"LOW_LIKE_RATE: {rates['like_rate']:.3f}")
                    return False, 0
                else:
                    logger.info(f"{tag} ✅ Passed Intelligence Gate (Like: {rates['like_rate']:.3f}). Proceeding to DISCOVERED.")
                self.state_manager.update_state(url, ReelState.DISCOVERED, title=meta.get('title', ''))
                state = ReelState.DISCOVERED
            else:
                logger.info(f"{tag} Skipping AI relevance check: Already completed.")

            # State 1: DISCOVERED -> DOWNLOADED
            if state in [ReelState.DOWNLOADED]:
                if not reel.get('gcs_uri'):
                    logger.warning(f"{tag} State is DOWNLOADED but gcs_uri is missing. Resetting to DISCOVERED.")
                    self.state_manager.update_state(url, ReelState.DISCOVERED)
                    state = ReelState.DISCOVERED
            
            if state in [ReelState.DISCOVERED, ReelState.FAILED]:
                if not reel.get('gcs_uri'):
                    random_jitter(label="Ingestion Prep")
                    logger.info(f"{tag} Downloading & uploading to GCS...")
                    # Execute atomic download & upload
                    result = self.downloader.download(url, filename_hint=reel.get('title', 'reel'))
                    if result.success:
                        gcs_uri = self.uploader.upload_file(result.video_path)
                        self.state_manager.update_state(url, ReelState.DOWNLOADED, gcs_uri=gcs_uri)
                        reel['gcs_uri'] = gcs_uri
                        state = ReelState.DOWNLOADED
                    else:
                        raise RuntimeError(f"Download failed: {result.error}")
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
                    
                    # 🛑 PAUSE PIPELINE HERE: Wait for manual dashboard approval
                    logger.info(f"{tag} ⏸️ Pausing pipeline for Dashboard manual approval.")
                    return True, 0
                else:
                    logger.info(f"{tag} Skipping Captioning: Metadata already exists.")
                    state = ReelState.CAPTIONED
                    return True, 0 # Already captioned, waiting for approval
            else:
                # If we skipped it, we don't return. We only skip if state was already past CAPTIONED.
                # Actually, if state was JOB_CREATED, it wouldn't enter this block, so we just pass.
                pass

            # State 3: JOB_CREATED (from Dashboard) -> MEDIA_PROCESSED
            # Note: We only enter here if the Dashboard set the state to JOB_CREATED
            if state in [ReelState.JOB_CREATED, ReelState.FAILED]:
                if not reel.get('job_id') and state == ReelState.JOB_CREATED:
                    logger.info(f"{tag} Creating Firestore job from dashboard approval...")
                    job_id = self.job_repo.create_job(reel['gcs_uri'], reel['ai_metadata'])
                    self.state_manager.update_state(url, ReelState.JOB_CREATED, job_id=job_id)
                    reel['job_id'] = job_id
                else:
                    pass
            else:
                pass

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

            # State 5: MEDIA_PROCESSED -> RELAYED_TO_PHONE / RELAYED_TO_FIREBASE
            if state == ReelState.MEDIA_PROCESSED:
                if not reel.get('state') == ReelState.RELAYED_TO_PHONE and not reel.get('state') == ReelState.RELAYED_TO_FIREBASE:
                    processed_uri = reel['processed_uri']
                    filename = os.path.basename(processed_uri)
                    local_processed_dir = os.path.join("data", "processed")
                    os.makedirs(local_processed_dir, exist_ok=True)
                    local_processed_path = os.path.join(local_processed_dir, filename)
                    
                    if not os.path.exists(local_processed_path):
                        logger.info(f"{tag} Downloading processed video from GCS for Relay sync...")
                        self.uploader.download_file(processed_uri, local_processed_path)
                    
                    # 1. Attempt LocalSend (Primary Relay)
                    logger.info(f"{tag} 🚀 Attempting LocalSend Relay to phone...")
                    relay_success = self.localsend_service.push([local_processed_path])
                    
                    if relay_success:
                        logger.info(f"{tag} ✅ Relayed to Phone via LocalSend!")
                        self.state_manager.update_state(url, ReelState.RELAYED_TO_PHONE)
                    else:
                        # 2. Fallback to Firebase Storage (Progressive Streaming)
                        logger.warning(f"{tag} ⚠️ LocalSend failed. Falling back to Firebase Storage...")
                        firebase_url = self.firebase_service.relay_video(local_processed_path)
                        
                        if firebase_url:
                            logger.info(f"{tag} ✅ Relayed to Firebase: {firebase_url}")
                            self.state_manager.update_state(url, ReelState.RELAYED_TO_FIREBASE, firebase_url=firebase_url)
                        else:
                            logger.error(f"{tag} ❌ Both LocalSend and Firebase Relay failed.")
                            self.state_manager.update_state(url, ReelState.FAILED, error_message="All relay methods failed")
                            return False, 0
                    
                    # 3. Trigger Optional HLS Transcoder Job for Adaptive Cloud Delivery (Method 1)
                    if self.hls_service.client and self.hls_service.cdn_host:
                        logger.info(f"{tag} 📡 Triggering HLS Transcode job for CDN streaming...")
                        # Transcoder needs a distinct output prefix
                        shortcode = url.strip('/').split('/')[-1] if '/' in url else "unknown"
                        output_prefix = f"gs://{self.video_service.bucket_name}/hls/{shortcode}/"
                        hls_url = self.hls_service.submit_and_wait(processed_uri, output_prefix)
                        if hls_url:
                            logger.info(f"{tag} ✅ HLS Manifest generated: {hls_url}")
                            self.state_manager.update_state(url, reel['state'], hls_cdn_url=hls_url)

                    return True, GAP_SECONDS
                else:
                    logger.info(f"{tag} Skipping Relay/Sync: Already synced or relayed.")
                    return False, 0
        
        except Exception as e:
            logger.error(f"{tag} 🚨 FATAL UNHANDLED ERROR for {url}: {e}", exc_info=True)
            self.state_manager.mark_failed(url, f"Fatal Error: {str(e)}")
            return False, 15 # Wait a bit before retry next reel
        
        return False, 0


def run():
    global TOTAL_REELS, GAP_SECONDS
    
    parser = argparse.ArgumentParser(description="Bulk Poster State Machine for Instagram Reels.")
    parser.add_argument("--count", type=int, default=TOTAL_REELS, help="Total reels to process")
    parser.add_argument("--gap", type=int, default=GAP_SECONDS, help="Wait time in seconds between posts")
    parser.add_argument("--retry-failed", action="store_true", help="Retry items in FAILED state")
    parser.add_argument("--no-youtube", action="store_true", help="Disable YouTube discovery")
    parser.add_argument("--min-views", type=int, help="Minimum views for discovery")
    parser.add_argument("--clear-dedup-discovery", action="store_true", help="Clear the discovery dedup database")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip hardware pre-flight checks")
    parser.add_argument("--config", type=str, default="config/cricket_manifest.yaml", help="Path to discovery manifest YAML")
    parser.add_argument("--db", type=str, help="Path to isolated state database (SQLite)")

    args = parser.parse_args()
    TOTAL_REELS = args.count
    GAP_SECONDS = args.gap

    logger.info(f"═══ Bulk Poster State Machine: {TOTAL_REELS} reels, {GAP_SECONDS//60}min gap ═══")
    
    if args.clear_dedup_discovery:
        db_path = os.path.join("data", "dedup.db")
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

    acquire_lock()
    try:
        sm = BulkPosterStateMachine(manifest_path=args.config, db_path=args.db)
        
        # 1. Fill queue if empty
        pending = sm.state_manager.get_pending_reels(include_failed=args.retry_failed)
        if len(pending) < TOTAL_REELS:
            needed = TOTAL_REELS - len(pending)
            logger.info(f"Queue needs {needed} more reels. Starting discovery...")
            sm.discover_new_content(needed, min_views=args.min_views)
        
        # 2. Process all pending items
        exclude_platforms = [Platform.YOUTUBE] if args.no_youtube else []
        sm.process_queue(
            retry_failed=args.retry_failed, 
            exclude_platforms=exclude_platforms, 
            min_views=args.min_views,
            args=args
        )
    finally:
        release_lock()


if __name__ == "__main__":
    run()
