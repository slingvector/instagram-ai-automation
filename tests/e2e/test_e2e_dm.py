"""
test_e2e_dm.py

End-to-end test:
1. Fetch up to 10 unread/unseen DMs using Playwright.
2. Extract Instagram Reel shortcodes from GraphQL.
3. Download the actual .mp4 files using yt-dlp via UniversalDownloader.
"""
import logging
import os
import sys
from pathlib import Path

# Load .env
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("test_e2e")

from src.ingestion.adapters.dm_adapter import DMAdapter
from src.ingestion.downloader import UniversalDownloader

def main():
    username = os.environ.get("IG_READONLY_USERNAME", "")
    if not username:
        logger.error("IG_READONLY_USERNAME not set in .env")
        sys.exit(1)

    logger.info("Starting E2E DM Pipeline Test...")
    
    # 1. Fetch items
    adapter = DMAdapter(headless=False, max_threads=5)
    items = adapter.fetch()
    
    if not items:
        logger.info("No items fetched. Did you clear the SQLite deduplication DB?")
        return
        
    # Limit to 10 items for the test
    items = items[:10]
    logger.info(f"Proceeding to download {len(items)} items...")
    
    # 2. Download items
    download_dir = Path("data/downloads")
    downloader = UniversalDownloader(output_dir=download_dir)
    
    success_count = 0
    for i, item in enumerate(items, 1):
        logger.info(f"[{i}/{len(items)}] Downloading: {item.url}")
        
        # Download with shortcode as hint
        result = downloader.download(item.url, filename_hint=item.shortcode)
        
        if result.success:
            logger.info(f"  ✅ SUCCESS: {result.video_path}")
            success_count += 1
            # You would usually do pHash dedup here: self.dedup.register_visual(...)
        else:
            logger.error(f"  ❌ FAILED: {result.error}")
            
    logger.info(f"E2E Test Complete. Successfully downloaded {success_count}/{len(items)} videos.")

if __name__ == "__main__":
    main()
