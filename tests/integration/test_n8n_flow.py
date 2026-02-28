"""
Integration test for MCR-203 n8n Orchestration Webhook.
Tests the full scraper → n8n → Cloud Function handoff by mocking n8n and the Cloud Function.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from scraper.controllers.scraper_controller import ScraperController


class TestScraperControllerIntegration:
    """Integration test for the full ingestion pipeline."""

    @pytest.mark.asyncio
    @patch("scraper.controllers.scraper_controller.GCSUploaderService")
    @patch("scraper.controllers.scraper_controller.WebhookService")
    @patch("scraper.controllers.scraper_controller.ProcessedReelsRepository")
    @patch("scraper.controllers.scraper_controller.PlaywrightScraperService")
    async def test_full_pipeline_new_reel(
        self, mock_scraper_cls, mock_repo_cls, mock_webhook_cls, mock_gcs_cls
    ):
        """New Reel: scrape → upload GCS → notify n8n → mark processed."""
        # --- Mock scraper returns one new URL
        mock_scraper = AsyncMock()
        mock_scraper.get_new_reel_urls.return_value = {
            "https://www.instagram.com/reel/TEST123/"
        }
        mock_scraper_cls.return_value = mock_scraper

        # --- Repo says URL is new
        mock_repo = MagicMock()
        mock_repo.is_url_processed.return_value = False
        mock_repo_cls.return_value = mock_repo

        # --- GCS upload succeeds
        mock_gcs = MagicMock()
        mock_gcs.download_and_upload.return_value = "gs://mcr-bucket/reels/reel_abc123.mp4"
        mock_gcs_cls.return_value = mock_gcs

        # --- Webhook send succeeds
        mock_webhook = MagicMock()
        mock_webhook.send_gcs_uri.return_value = True
        mock_webhook_cls.return_value = mock_webhook

        controller = ScraperController()
        await controller.run_ingestion_pipeline()

        # Assertions
        mock_scraper.get_new_reel_urls.assert_called_once()
        mock_repo.is_url_processed.assert_called_once_with("https://www.instagram.com/reel/TEST123/")
        mock_gcs.download_and_upload.assert_called_once_with("https://www.instagram.com/reel/TEST123/")
        mock_webhook.send_gcs_uri.assert_called_once_with("gs://mcr-bucket/reels/reel_abc123.mp4")
        mock_repo.mark_url_processed.assert_called_once_with("https://www.instagram.com/reel/TEST123/")

    @pytest.mark.asyncio
    @patch("scraper.controllers.scraper_controller.GCSUploaderService")
    @patch("scraper.controllers.scraper_controller.WebhookService")
    @patch("scraper.controllers.scraper_controller.ProcessedReelsRepository")
    @patch("scraper.controllers.scraper_controller.PlaywrightScraperService")
    async def test_pipeline_skips_already_processed(
        self, mock_scraper_cls, mock_repo_cls, mock_webhook_cls, mock_gcs_cls
    ):
        """Already-seen Reels should be skipped without GCS upload or n8n call."""
        mock_scraper = AsyncMock()
        mock_scraper.get_new_reel_urls.return_value = {
            "https://www.instagram.com/reel/OLD123/"
        }
        mock_scraper_cls.return_value = mock_scraper

        mock_repo = MagicMock()
        mock_repo.is_url_processed.return_value = True
        mock_repo_cls.return_value = mock_repo

        mock_gcs = MagicMock()
        mock_gcs_cls.return_value = mock_gcs

        mock_webhook = MagicMock()
        mock_webhook_cls.return_value = mock_webhook

        controller = ScraperController()
        await controller.run_ingestion_pipeline()

        mock_gcs.download_and_upload.assert_not_called()
        mock_webhook.send_gcs_uri.assert_not_called()
        mock_repo.mark_url_processed.assert_not_called()

    @pytest.mark.asyncio
    @patch("scraper.controllers.scraper_controller.GCSUploaderService")
    @patch("scraper.controllers.scraper_controller.WebhookService")
    @patch("scraper.controllers.scraper_controller.ProcessedReelsRepository")
    @patch("scraper.controllers.scraper_controller.PlaywrightScraperService")
    async def test_pipeline_does_not_mark_processed_on_webhook_failure(
        self, mock_scraper_cls, mock_repo_cls, mock_webhook_cls, mock_gcs_cls
    ):
        """If n8n webhook fails, URL should NOT be marked processed (retry next run)."""
        mock_scraper = AsyncMock()
        mock_scraper.get_new_reel_urls.return_value = {
            "https://www.instagram.com/reel/NEW456/"
        }
        mock_scraper_cls.return_value = mock_scraper

        mock_repo = MagicMock()
        mock_repo.is_url_processed.return_value = False
        mock_repo_cls.return_value = mock_repo

        mock_gcs = MagicMock()
        mock_gcs.download_and_upload.return_value = "gs://mcr-bucket/reels/reel_xyz.mp4"
        mock_gcs_cls.return_value = mock_gcs

        mock_webhook = MagicMock()
        mock_webhook.send_gcs_uri.return_value = False   # n8n failed
        mock_webhook_cls.return_value = mock_webhook

        controller = ScraperController()
        await controller.run_ingestion_pipeline()

        mock_repo.mark_url_processed.assert_not_called()
