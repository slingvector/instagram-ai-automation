"""
test_e2e_cross_platform.py
"""
import logging
import os
import sys

# Load .env
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("test_cross_platform")

from src.ingestion.adapters.cross_platform_adapter import CrossPlatformAdapter

def main():
    logger.info("Starting Cross-Platform Adapter Test...")
    
    # Run fetch on default config 
    # we set max_items_per_query=2 to keep the test quick
    adapter = CrossPlatformAdapter(max_items_per_query=2)
    items = adapter.fetch()
    
    if not items:
        logger.info("No items fetched. Config might be empty or all items are duplicates.")
        return
        
    logger.info(f"✅ Successfully extracted {len(items)} cross-platform items:")
    for i, item in enumerate(items, 1):
        logger.info(f"  {i}. {item.platform.upper()} - {item.url}")
        logger.info(f"     Niche: {item.niche} | Views: {item.view_count} | Query: {item.raw_metadata.get('query')}")

    logger.info("\n--- Commencing Actual Video Download Test (First 3 items) ---")
    
    from src.ingestion.downloader import UniversalDownloader
    from pathlib import Path
    
    downloader = UniversalDownloader(output_dir=Path("data/downloads/cross_platform"))
    success_count = 0
    
    for i, item in enumerate(items[:3], 1):
        logger.info(f"[{i}/3] Downloading {item.platform} video: {item.url}")
        result = downloader.download(item.url, filename_hint=f"{item.platform}_{i}")
        
        if result.success:
            logger.info(f"  ✅ SUCCESS: {result.video_path}")
            success_count += 1
        else:
            logger.error(f"  ❌ FAILED: {result.error}")
            
    logger.info(f"Cross-platform download test complete. {success_count}/3 videos saved.")

if __name__ == "__main__":
    main()
