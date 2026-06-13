import logging
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class IGMessagingRepository:
    """
    Repository layer for interacting with the Official Meta Messaging API.
    Follows SRP by concentrating purely on the HTTP transmission of direct 
    messages and comment replies.
    """

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("IG_GRAPH_ACCESS_TOKEN")
        self.base_url = "https://graph.facebook.com/v19.0"
        self.session = self._build_session()

        if not self.access_token:
            logger.warning("No IG_GRAPH_ACCESS_TOKEN provided. IGMessagingRepository calls will fail.")

    def _build_session(self) -> requests.Session:
        """Resilient HTTP session with exponential backoff for messaging reliability."""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def reply_to_comment(self, comment_id: str, message_text: str) -> Dict[str, Any]:
        """
        Uses the /{ig_comment_id}/replies endpoint to post an automated 
        reply to a specific comment.
        """
        url = f"{self.base_url}/{comment_id}/replies"
        data = {
            "message": message_text,
            "access_token": self.access_token
        }
        return self._execute_post(url, data)

    def send_direct_message(self, recipient_ig_id: str, message_text: str) -> Dict[str, Any]:
        """
        Uses the IG Messaging API to send a DM to a user (e.g. delivering a lead magnet).
        Must comply with the 24-hour standard messaging window policy.
        """
        # Note: The actual Meta endpoint requires the IG User ID associated with the Professional Account
        # For simplicity in this architecture demo, we assume the user_id is the PAGE's IG ID 
        # But specifically routing it through the /messages endpoint.
        ig_user_id = os.getenv("IG_USER_ID", "me")
        url = f"{self.base_url}/{ig_user_id}/messages"
        data = {
            "recipient": {"id": recipient_ig_id},
            "message": {"text": message_text},
            "access_token": self.access_token
        }
        return self._execute_post(url, data)

    def _execute_post(self, url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Executes the POST request with standardized error handling."""
        try:
            response = self.session.post(url, json=data, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTPError in IGMessagingRepository: {e.response.text}")
            raise RuntimeError(f"Messaging API Error: {e.response.text}") from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error in IGMessagingRepository: {e}")
            raise RuntimeError(f"Network error: {e}") from e
