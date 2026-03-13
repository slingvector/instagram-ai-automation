from flask import jsonify
import logging
import os
from dotenv import load_dotenv
load_dotenv()

from src.media_factory.repositories.processed_job_repository import ProcessedJobRepository
from src.media_factory.services.video_processor_service import VideoProcessorService

logger = logging.getLogger(__name__)

def process_job(job_id: str):
    """
    Controller logic to orchestrate downloading, processing, and uploading.
    """
    project_id = os.environ.get("GCP_PROJECT_ID", "mcr-relay-1772228380")
    
    try:
        # Initialize Services and Repositories
        firestore_repo = ProcessedJobRepository(project_id=project_id)
        video_service = VideoProcessorService(project_id=project_id)
        
        # 1. Fetch Job from Firestore
        logger.info(f"Fetching job {job_id} from Firestore")
        job_data = firestore_repo.get_job(job_id)
        if not job_data:
             return jsonify({"error": "Job not found"}), 404
             
        # 2. Extract metadata
        ai_metadata = job_data.get("ai_metadata", {})
        burn_in_text = ai_metadata.get("burn_in_text", "")
        caption_text = ai_metadata.get("caption", "")
        raw_video_uri = job_data.get("gcs_raw_video_uri", "")
        
        if not raw_video_uri:
             logger.error(f"Job {job_id} is missing raw video URI")
             return jsonify({"error": "Invalid job state: missing video uri"}), 400
             
        # 3. Process the video
        logger.info(f"Starting video processing pipeline for: {raw_video_uri}")
        processed_uri, tx_receipt = video_service.apply_burn_in(raw_video_uri, burn_in_text, caption_text, job_id)
        
        # 4. Update Firestore Status
        logger.info(f"Updating job {job_id} status to READY_FOR_PUBLISHING")
        firestore_repo.mark_job_completed(job_id, processed_uri, tx_receipt)
        
        return jsonify({
            "status": "success", 
            "job_id": job_id, 
            "processed_video_uri": processed_uri,
            "digital_passport_tx_hash": tx_receipt
        }), 200
        
    except Exception as e:
        logger.error(f"Error processing job {job_id}: {e}")
        return jsonify({"error": "Internal Server Error"}), 500
