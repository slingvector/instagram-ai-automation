import logging
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ThreadsGraphRepository:
    """
    Repository layer for interacting with the Official Meta Threads API.
    Follows SRP by handling HTTP communication and resilient retry mechanisms.
    """

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("THREADS_ACCESS_TOKEN")
        self.user_id = os.getenv("THREADS_USER_ID", "me")
        self.base_url = "https://graph.threads.net/v1.0"
        self.session = self._build_session()

        if not self.access_token:
            logger.warning("No THREADS_ACCESS_TOKEN provided. ThreadsGraphRepository calls will fail.")

    def _build_session(self) -> requests.Session:
        """Configures a resilient HTTP session with exponential backoff retries."""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def create_text_container(self, text: str) -> Dict[str, Any]:
        """Creates a Threads media container for a text-only post."""
        url = f"{self.base_url}/{self.user_id}/threads"
        data = {
            "media_type": "TEXT",
            "text": text,
            "access_token": self.access_token
        }
        return self._execute_post(url, data)

    def publish_container(self, creation_id: str) -> Dict[str, Any]:
        """Publishes a previously created Threads media container."""
        url = f"{self.base_url}/{self.user_id}/threads_publish"
        data = {
            "creation_id": creation_id,
            "access_token": self.access_token
        }
        return self._execute_post(url, data)

    def _execute_post(self, url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Executes the HTTP POST request with centralized error handling."""
        try:
            response = self.session.post(url, data=data, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTPError in ThreadsGraphRepository: {e.response.text}")
            raise RuntimeError(f"Threads API Error: {e.response.text}") from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error in ThreadsGraphRepository: {e}")
            raise RuntimeError(f"Network error: {e}") from e
