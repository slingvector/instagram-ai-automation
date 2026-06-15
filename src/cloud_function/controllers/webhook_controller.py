from flask import jsonify, Request
import logging
import os
from src.cloud_function.services.vertex_ai_service import VertexAIService
from src.cloud_function.repositories.job_repository import JobRepository

from src.cloud_function.services.media_factory_trigger_service import MediaFactoryTriggerService

logger = logging.getLogger(__name__)

def process_webhook(request: Request):
    """
    Controller layer for handling the incoming webhook from n8n.
    Validates input and orchestrates the Vertex AI and Firestore services.
    """
    request_json = request.get_json(silent=True)
    
    if not request_json or 'gcs_video_uri' not in request_json:
        logger.error("Invalid Request: Missing 'gcs_video_uri' in payload.")
        return jsonify({"error": "Bad Request: Missing 'gcs_video_uri'"}), 400
        
    gcs_uri = request_json['gcs_video_uri']
    logger.info(f"Received webhook for video: {gcs_uri}")
    
    project_id = os.environ.get("GCP_PROJECT_ID", "")
    factory_url = os.environ.get("MEDIA_FACTORY_URL", "https://mcr-media-factory-1068721430700.us-central1.run.app")
    
    try:
        # Initialize Services and Repositories
        vertex_service = VertexAIService(project_id=project_id)
        firestore_repo = JobRepository(project_id=project_id)
        factory_trigger = MediaFactoryTriggerService(target_url=factory_url)
        
        # Call Vertex AI
        metadata = vertex_service.analyze_video(gcs_uri)
        
        # Save to Firestore
        job_id = firestore_repo.create_job(gcs_uri, metadata)
        
        # Trigger Media Factory Cloud Run Worker
        trigger_success = factory_trigger.trigger_processing(job_id)
        if not trigger_success:
             logger.warning(f"Job {job_id} was saved to Firestore but the downstream Media Factory trigger failed.")
             
        return jsonify({"status": "success", "job_id": job_id, "message": "Video accepted and processing queued."}), 200
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({"error": "Internal Server Error"}), 500
