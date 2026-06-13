"""
Unit tests for WebhookService and GCSUploaderService.
MCR-203: n8n Orchestration Webhook
"""
import pytest
from unittest.mock import patch, MagicMock
import requests

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from scraper.services.webhook_service import WebhookService
from scraper.services.gcs_uploader_service import GCSUploaderService


class TestWebhookService:
    """Tests for WebhookService."""

    def test_send_gcs_uri_success(self):
        """Should POST gcs_video_uri and return True on 200."""
        service = WebhookService(webhook_url="http://localhost:5679/webhook/mcr-ingest")
        with patch("scraper.services.webhook_service.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            result = service.send_gcs_uri("gs://mcr-bucket/reels/reel_abc123.mp4")

            mock_post.assert_called_once_with(
                "http://localhost:5679/webhook/mcr-ingest",
                json={"gcs_video_uri": "gs://mcr-bucket/reels/reel_abc123.mp4"},
                timeout=30,
            )
            assert result is True

    def test_send_gcs_uri_no_webhook_url(self):
        """Should return False and log warning if webhook URL is not set."""
        service = WebhookService(webhook_url="")
        result = service.send_gcs_uri("gs://mcr-bucket/reels/reel_abc123.mp4")
        assert result is False

    def test_send_gcs_uri_request_error(self):
        """Should return False on network error."""
        service = WebhookService(webhook_url="http://localhost:5679/webhook/mcr-ingest")
        with patch("scraper.services.webhook_service.requests.post",
                   side_effect=requests.exceptions.ConnectionError("refused")):
            result = service.send_gcs_uri("gs://mcr-bucket/reels/reel_abc123.mp4")
            assert result is False

    def test_send_gcs_uri_http_error(self):
        """Should return False on non-200 HTTP response."""
        service = WebhookService(webhook_url="http://localhost:5679/webhook/mcr-ingest")
        with patch("scraper.services.webhook_service.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500")
            mock_post.return_value = mock_response

            result = service.send_gcs_uri("gs://mcr-bucket/reels/reel_abc123.mp4")
            assert result is False


class TestGCSUploaderService:
    """Tests for GCSUploaderService."""

    @patch("scraper.services.gcs_uploader_service.storage.Client")
    def test_download_and_upload_success(self, mock_storage_client):
        """Should call yt-dlp, upload to GCS, and return correct gs:// URI."""
        # Setup mock GCS bucket
        mock_client = MagicMock()
        mock_storage_client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        service = GCSUploaderService(bucket_name="test-bucket")

        with patch("scraper.services.gcs_uploader_service.subprocess.run") as mock_run, \
             patch("scraper.services.gcs_uploader_service.os.path.exists", return_value=True):

            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="30.5\n")

            result = service.download_and_upload("https://www.instagram.com/reel/TEST123/")

            # Service now returns (gcs_uri, duration) tuple
            gcs_uri, duration = result

            # yt-dlp should be the first call
            first_call_args = mock_run.call_args_list[0][0][0]
            assert "yt-dlp" in first_call_args
            assert "https://www.instagram.com/reel/TEST123/" in first_call_args

            # ffprobe is called second for duration detection
            assert mock_run.call_count >= 2

            # GCS upload called
            mock_blob.upload_from_filename.assert_called_once()

            # URI format correct
            assert gcs_uri.startswith("gs://test-bucket/reels/reel_")
            assert gcs_uri.endswith(".mp4")

    @patch("scraper.services.gcs_uploader_service.storage.Client")
    def test_download_failure_raises(self, mock_storage_client):
        """Should raise RuntimeError if yt-dlp exits non-zero."""
        mock_storage_client.return_value = MagicMock()
        service = GCSUploaderService(bucket_name="test-bucket")

        with patch("scraper.services.gcs_uploader_service.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="yt-dlp: error")

            with pytest.raises(RuntimeError, match="yt-dlp download failed"):
                service.download_and_upload("https://www.instagram.com/reel/BADURL/")
