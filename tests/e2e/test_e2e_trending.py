"""
test_e2e_trending.py
"""
import logging
import sys

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("test_trending")

def main():
    logger.info("Starting Trending Monitor Adapter Test...")
    
    from src.ingestion.adapters.trending_adapter import TrendingAdapter
    
    # We use the real configuration to hit all configured endpoints
    adapter = TrendingAdapter()
    
    # Clear previously seen things if we want a fresh run in test
    # (Optional, but good for local debugging)
    # adapter.dedup._conn.execute("DELETE FROM seen_dm_ids WHERE message_id LIKE 'reddit::%' OR message_id LIKE 'rss::%' OR message_id LIKE 'yt_trending::%'")
    # adapter.dedup._conn.commit()
    
    items = adapter.fetch()
    
    if not items:
        logger.info("No viral trends fetched. (Perhaps all seen or filters too high)")
        return
        
    logger.info(f"✅ Successfully extracted {len(items)} trending items:")
    
    for i, item in enumerate(items, 1):
        logger.info(f"  {i}. [{item.platform}] - {item.title}")
        logger.info(f"     URL: {item.url} | Niche: {item.niche} | Views/Ups: {item.view_count}")
        logger.info(f"     Text Prompt: {item.raw_metadata.get('text_prompt')}")
        logger.info("-" * 40)
        
    logger.info("\n--- Commencing Video Download Test (First 2 generic text items) ---")
    
    # Filter for the items that use the generic B-roll
    text_items = [i for i in items if i.platform == "web" or (i.platform == "reddit" and not i.raw_metadata.get("is_video"))]
    
    from src.ingestion.downloader import UniversalDownloader
    from pathlib import Path
    
    downloader = UniversalDownloader(output_dir=Path("data/downloads/trending"))
    success_count = 0
    
    for i, item in enumerate(text_items[:2], 1):
        logger.info(f"[{i}/2] Downloading trending video B-roll for: {item.title}")
        result = downloader.download(item.url, filename_hint=f"trend_{item.platform}_{i}")
        
        if result.success:
            logger.info(f"  ✅ SUCCESS: {result.video_path}")
            success_count += 1
        else:
            logger.error(f"  ❌ FAILED: {result.error}")
            
    logger.info(f"Trending download test complete. {success_count}/2 fallback B-roll videos saved.")

if __name__ == "__main__":
    main()
