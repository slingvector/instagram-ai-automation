"""
test_e2e_creator.py
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
logger = logging.getLogger("test_creator")


def main():
    logger.info("Starting Creator Watchlist Adapter Test...")
    
    # We need to ensure we run headless=False if we want to debug, but headless=True is fine if session works.
    from src.ingestion.adapters.creator_adapter import CreatorAdapter
    
    # To prevent hitting every creator in our config during the test, we'll override the config
    # to only look at one or two creators. We can do this by creating a temp config just for the test.
    import tempfile
    import yaml
    
    test_config = {
        "filters": {
            "min_views": 100000, # Lower threshold for test
            "min_likes": 1000
        },
        "creators": {
            "entertainment": ["complex"],
            "fun": ["daquan"]
        }
    }
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(test_config, f)
        temp_config_path = f.name
        
    try:
        adapter = CreatorAdapter(config_paths=[temp_config_path], headless=True)
        items = adapter.fetch()
        
        if not items:
            logger.info("No new viral items fetched from creators.")
        else:
            logger.info(f"✅ Successfully extracted {len(items)} viral creator items:")
            for i, item in enumerate(items, 1):
                logger.info(f"  {i}. {item.platform.upper()} - {item.url}")
                logger.info(f"     Niche: {item.niche} | Views: {item.view_count} | Likes: {item.like_count} | Creator: {item.raw_metadata.get('creator')}")

            logger.info("\n--- Commencing Actual Video Download Test (First 3 items) ---")
            
            from src.ingestion.downloader import UniversalDownloader
            from pathlib import Path
            
            downloader = UniversalDownloader(output_dir=Path("data/downloads/creators"))
            success_count = 0
            
            for i, item in enumerate(items[:3], 1):
                logger.info(f"[{i}/3] Downloading creator video: {item.url}")
                result = downloader.download(item.url, filename_hint=f"creator_{item.raw_metadata.get('creator')}_{item.shortcode}")
                
                if result.success:
                    logger.info(f"  ✅ SUCCESS: {result.video_path}")
                    success_count += 1
                else:
                    logger.error(f"  ❌ FAILED: {result.error}")
                    
            logger.info(f"Creator download test complete. {success_count}/3 videos saved.")
    finally:
        os.unlink(temp_config_path)

if __name__ == "__main__":
    main()
