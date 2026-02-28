import logging
import requests

logger = logging.getLogger(__name__)

class WebhookService:
    """
    Service layer responsible for external API communications (n8n webhook).
    Sends processed GCS URIs to the n8n orchestration layer.
    """
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_gcs_uri(self, gcs_video_uri: str) -> bool:
        """
        Sends the GCS video URI to the n8n orchestration webhook.
        n8n then forwards it to the Cloud Function for AI processing.
        """
        if not self.webhook_url:
            logger.warning("Webhook URL is not set! Skipping delivery.")
            return False

        payload = {"gcs_video_uri": gcs_video_uri}
        try:
            response = requests.post(self.webhook_url, json=payload, timeout=30)
            response.raise_for_status()
            logger.info(f"Successfully posted {gcs_video_uri} to n8n: {response.status_code}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to post to n8n webhook: {e}")
            return False
