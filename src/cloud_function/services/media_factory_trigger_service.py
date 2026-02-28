import os
import requests
import logging

logger = logging.getLogger(__name__)

class MediaFactoryTriggerService:
    """
    Service responsible for triggering the downstream Media Factory Cloud Run instance
    after AI Processing is complete.
    """
    def __init__(self, target_url: str):
        self.target_url = target_url

    def trigger_processing(self, job_id: str) -> bool:
        """Sends a POST webhook to the Cloud Run service to begin FFmpeg rendering."""
        try:
            logger.info(f"Triggering Media Factory for Job: {job_id}")
            # Note: In a true prod environment where Cloud Run is strictly authenticated, 
            # we would implement google-auth to inject an OIDC token here.
            # Currently, the endpoint is --allow-unauthenticated as per script.
            payload = {"job_id": job_id}
            response = requests.post(self.target_url, json=payload, timeout=120)
            
            if response.status_code == 200:
                logger.info(f"Media Factory accepted job {job_id}.")
                return True
            else:
                logger.error(f"Media Factory rejected job {job_id}: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to communicate with Media Factory: {e}")
            return False
