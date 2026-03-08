import os
import sys
import time
import logging
from dotenv import load_dotenv

# Ensure the src directory is available
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ingestion.adapters.trending_adapter import TrendingAdapter
from src.scraper.services.gcs_uploader_service import GCSUploaderService
from src.cloud_function.services.vertex_ai_service import VertexAIService
from src.cloud_function.repositories.job_repository import JobRepository
from src.publishing_edge.controllers.posting_controller import PostingController
from src.publishing_edge.services.adb_client import ADBClient
from src.publishing_edge.config import DEVICE_UDID

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("e2e_geopolitics_test")

def run_e2e_test():
    logger.info("=== Starting Geopolitics End-to-End Test from Scratch ===")
    
    # 1. Ingestion: Find 1 Geopolitics SEO Hit
    logger.info("Step 1: Ingestion Pipeline")
    trending_adapter = TrendingAdapter()
    items = trending_adapter.fetch()
    
    if not items:
        logger.error("No trending items found based on SEO terms. Aborting test.")
        return
        
    target_item = items[0]
    logger.info(f"Target selected: {target_item.title} ({target_item.url})")
    
    # 2. Downloader & Cloud Uploader
    logger.info("Step 2: Downloading & GCS Upload")
    bucket_name = os.getenv("GCS_BUCKET_NAME", "mcr-relay-1772228380-raw-input")
    uploader = GCSUploaderService(bucket_name=bucket_name)
    gcs_uri = uploader.download_and_upload(target_item.url)
    logger.info(f"Video uploaded to: {gcs_uri}")
    
    # 3. AI Copilot: Generate Caption via Vertex AI
    logger.info("Step 3: Vertex AI Copilot Caption Generation")
    project_id = os.getenv("GCP_PROJECT_ID", "mcr-relay-1772228380")
    ai_service = VertexAIService(project_id=project_id)
    metadata = ai_service.analyze_video(gcs_uri)
    logger.info(f"Generated AI Metadata: {metadata}")
    
    # 4. Database: Create Job Record
    logger.info("Step 4: Writing Job to Firestore")
    job_repo = JobRepository(project_id=project_id)
    job_id = job_repo.create_job(gcs_uri, metadata)
    
    # We must reset the job status so the posting controller automatically picks it up
    logger.info(f"Job {job_id} created. Bypassing media_factory and setting to READY_FOR_PUBLISHING.")
    db = job_repo.db
    db.collection("job_queue").document(job_id).update({"status": "READY_FOR_PUBLISHING"})
    
    # 5. Device Edge: Clear Instagram and Post
    logger.info("Step 5: Publishing Edge Executing")
    logger.info("Force stopping Instagram to ensure clean state...")
    ADBClient(DEVICE_UDID).stop_instagram()
    time.sleep(2)
    
    controller = PostingController()
    try:
        controller.execute(job_id)
        logger.info("=== End-to-End Test Completed Successfully ===")
    except Exception as e:
        logger.error(f"Failed during Appium Execution: {e}")

if __name__ == "__main__":
    run_e2e_test()
