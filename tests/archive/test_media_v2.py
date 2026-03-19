import logging
import os
from src.media_factory.services.video_processor_service import VideoProcessorService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_media_pipeline():
    project_id = "mcr-relay-1772228380"
    service = VideoProcessorService(project_id)
    
    # Test with a known relevant reel
    raw_video_uri = "gs://mcr-relay-1772228380-raw-input/reels/reel_8f670b31.mp4" # Re-using for now, but will check if I can find a 16:9 asset
    text = "THE ANCIENT ARCHITECTURE OF EGYPT REVEALS SECRETS OF THE PAST"
    caption_text = "Masterpieces of the ancient world. #history #architecture #egypt"
    job_id = "test_creator_std_v2_5_landscape"
    niche = "history"
    
    logger.info("Starting Ultra-Pro v2 Verification Test...")
    try:
        processed_uri, tx_receipt = service.apply_burn_in(raw_video_uri, text, caption_text, job_id, niche=niche)
        logger.info(f"✅ Success! Processed URI: {processed_uri}")
        logger.info(f"✅ Blockchain Hash: {tx_receipt}")
    except Exception as e:
        logger.error(f"❌ Verification Failed: {e}")

if __name__ == "__main__":
    test_media_pipeline()
