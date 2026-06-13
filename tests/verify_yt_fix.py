import os
import sys
import logging
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from src.scraper.services.gcs_uploader_service import GCSUploaderService

def verify():
    # A URL that failed previously due to bot detection
    test_url = "https://www.youtube.com/watch?v=7FwDMzIbZrg"
    bucket = os.getenv("GCS_BUCKET_NAME")
    
    logger.info(f"Testing authenticated download for: {test_url}")
    uploader = GCSUploaderService(bucket_name=bucket)
    
    try:
        gcs_uri, duration = uploader.download_and_upload(test_url)
        logger.info(f"✅ Success! GCS URI: {gcs_uri}, Duration: {duration}")
    except Exception as e:
        logger.error(f"❌ Failed: {e}")

if __name__ == "__main__":
    verify()
