# scripts/run_art_erotica_scrape.py
import logging
import sys
import os
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from src.ingestion.adapters.creator_adapter import CreatorAdapter
from src.orchestration.state_manager import StateManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Initializing run_art_erotica_scrape...")
    
    # Instantiate the CreatorAdapter targeting our new manifest
    manifest_path = "config/art_erotica_manifest.yaml"
    if not os.path.exists(manifest_path):
        logger.error(f"Manifest not found at {manifest_path}")
        sys.exit(1)
        
    adapter = CreatorAdapter(config_paths=[manifest_path])
    state_manager = StateManager()
    
    # We will fetch a few reels in broad_mode to populate the database
    logger.info("Starting CreatorAdapter fetch in broad_mode=True...")
    added_count = 0
    max_reels_to_add = 10
    
    try:
        # fetch using a low minimum view filter so we capture any recent reels
        for item in adapter.fetch(min_views=10000, broad_mode=True):
            logger.info(f"Discovered: {item.url} (Niche: {item.niche})")
            
            # Persist to local bulk_post_state.db
            inserted = state_manager.add_discovered_reel(
                url=item.url,
                title=item.title or f"Art Erotica Reel by @{item.url.split('/')[-2] if '/' in item.url else 'creator'}",
                platform="instagram",
                source="art_erotica_scrape",
                niche=item.niche
            )
            
            if inserted:
                logger.info(f"✅ Registered Reel in Database: {item.url}")
                added_count += 1
            else:
                logger.info(f"ℹ️ Reel already existed in Database: {item.url}")
                
            if added_count >= max_reels_to_add:
                logger.info(f"Reached cap of {max_reels_to_add} added reels. Stopping scrape.")
                break
                
        logger.info(f"Successfully scraped and added {added_count} reels to local database.")
        
    except Exception as e:
        logger.exception(f"Error during scrape execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
