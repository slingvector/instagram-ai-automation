import logging
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class IGGraphRepository:
    """
    Repository layer for interacting with the Official Instagram Graph API.
    Follows SRP (Single Responsibility Principle) by exclusively handling HTTP communication,
    retries, and basic error parsing. It does not contain business logic.
    """

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("IG_GRAPH_ACCESS_TOKEN")
        self.base_url = "https://graph.facebook.com/v19.0"
        self.session = self._build_session()

        if not self.access_token:
            logger.warning("No IG_GRAPH_ACCESS_TOKEN provided. IGGraphRepository calls will fail.")

    def _build_session(self) -> requests.Session:
        """Configures a resilient HTTP session with exponential backoff retries."""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def get_user_media(self, ig_user_id: str, limit: int = 50) -> Dict[str, Any]:
        """Fetches recent media objects for the given IG user."""
        url = f"{self.base_url}/{ig_user_id}/media"
        params = {
            "fields": "id,caption,media_type,timestamp,shortcode",
            "access_token": self.access_token,
            "limit": limit
        }
        return self._execute_get(url, params)

    def get_media_insights(self, media_id: str) -> Dict[str, Any]:
        """Fetches detailed performance metrics for a specific media object (Reel)."""
        url = f"{self.base_url}/{media_id}/insights"
        params = {
            "metric": "reach,plays,likes,comments,shares,saved",
            "access_token": self.access_token
        }
        return self._execute_get(url, params)

    def _execute_get(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Executes the HTTP GET request with centralized error handling."""
        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTPError in IGGraphRepository: {e.response.text}")
            raise RuntimeError(f"Graph API Error: {e.response.text}") from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error in IGGraphRepository: {e}")
            raise RuntimeError(f"Network error: {e}") from e
