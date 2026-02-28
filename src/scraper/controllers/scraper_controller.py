import asyncio
import logging
import os
from src.scraper.config import (
    N8N_WEBHOOK_URL, TARGET_INSTAGRAM_CHAT_URL,
    USER_DATA_DIR, HEADLESS, PROXY_SERVER, DB_PATH,
    GCS_BUCKET_NAME, GOOGLE_APPLICATION_CREDENTIALS
)
from src.scraper.services.playwright_scraper_service import PlaywrightScraperService
from src.scraper.services.webhook_service import WebhookService
from src.scraper.services.gcs_uploader_service import GCSUploaderService
from src.scraper.repositories.processed_reels_repository import ProcessedReelsRepository

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ScraperController:
    """
    Controller layer that orchestrates the full edge-ingestion pipeline:
      1. Scrape Instagram DMs for Reel URLs
      2. Deduplicate against local SQLite DB
      3. Download Reel video via yt-dlp
      4. Upload to GCS
      5. Notify n8n orchestrator with GCS URI
    """
    def __init__(self):
        self.repository = ProcessedReelsRepository(db_path=DB_PATH)
        self.scraper_service = PlaywrightScraperService(
            target_url=TARGET_INSTAGRAM_CHAT_URL,
            user_data_dir=USER_DATA_DIR,
            headless=HEADLESS,
            proxy_server=PROXY_SERVER
        )
        self.gcs_uploader = GCSUploaderService(
            bucket_name=GCS_BUCKET_NAME,
            credentials_path=GOOGLE_APPLICATION_CREDENTIALS
        )
        self.webhook_service = WebhookService(webhook_url=N8N_WEBHOOK_URL)

    async def run_ingestion_pipeline(self):
        """Executes the full edge-ingestion pipeline."""
        logger.info("Starting MCR Edge Ingestion Pipeline...")

        # 1. Scrape the DOM for Reel URLs
        extracted_urls = await self.scraper_service.get_new_reel_urls()

        if not extracted_urls:
            logger.info("Pipeline complete. No incoming Reels found in the current view.")
            return

        logger.info(f"Found {len(extracted_urls)} Reel URL(s) in the DOM.")

        # 2. Process each URL
        for url in extracted_urls:
            # 2a. Deduplication check
            if self.repository.is_url_processed(url):
                logger.debug(f"Already processed, skipping: {url}")
                continue

            logger.info(f"New Reel discovered: {url}")

            try:
                # 2b. Download and upload to GCS
                gcs_uri = self.gcs_uploader.download_and_upload(url)
                logger.info(f"Reel uploaded to GCS: {gcs_uri}")

                # 2c. Notify n8n with the GCS URI
                success = self.webhook_service.send_gcs_uri(gcs_uri)

                if success:
                    # 2d. Mark as processed only after successful hand-off
                    self.repository.mark_url_processed(url)
                    logger.info(f"Pipeline complete for: {url}")
                else:
                    logger.error(f"n8n notification failed for {url}, will retry on next run.")

            except Exception as e:
                logger.error(f"Failed to process Reel {url}: {e}", exc_info=True)


if __name__ == "__main__":
    controller = ScraperController()
    asyncio.run(controller.run_ingestion_pipeline())
