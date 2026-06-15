import logging
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from src.ingestion.adapters.creator_adapter import CreatorAdapter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_fetch():
    # Use a known elite account
    adapter = CreatorAdapter(config_paths=[])
    # Mock some config for the adapter
    adapter.watchlists = {
        "filters": {"min_views": 1000000, "min_likes": 1000},
        "creators": {"adrenaline": ["nimsdai"]}
    }
    
    logger.info("Starting CreatorAdapter fetch for @nimsdai...")
    found_any = False
    for item in adapter.fetch(min_views=1000000):
        logger.info(f"✅ Found viral reel: {item.url} - Views: {item.view_count}")
        found_any = True
    
    if not found_any:
        logger.warning("No viral reels found for @nimsdai.")

if __name__ == "__main__":
    test_fetch()
