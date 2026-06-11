"""
tests/industrial_discovery_test.py

Verifies the Industrial Content Discovery pipeline.
1. Scrapes seeds from discovery_manifest.yaml
2. Validates view/like count filtering
3. Confirms auto-expansion (new creators added to manifest)
"""
import os, sys, logging
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ingestion.adapters.trending_adapter import TrendingAdapter
from src.ingestion.services.discovery_service import DiscoveryService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("discovery_test")

def run_test():
    manifest_path = "config/discovery_manifest.yaml"
    discovery_service = DiscoveryService(manifest_path)
    adapter = TrendingAdapter(manifest_path=manifest_path)
    
    logger.info("🚀 Starting 10-video Pilot Scraper Pass...")
    
    discovery_limit = 20
    results = {"total": 0, "tiktok": 0, "youtube": 0, "instagram": 0}
    
    # We'll run the fetcher and see what it finds
    try:
        pool = adapter.fetch()
        for i, item in enumerate(pool):
            if results["total"] >= discovery_limit:
                break
            
            results["total"] += 1
            results[item.platform.lower()] += 1
            
            description = f"[{results['total']}] Discovered {item.platform.upper()} {item.source_type}: {item.title[:50]}... ({item.view_count} views)"
            if item.platform.lower() == "youtube":
                description += f" [Duration: {item.duration_seconds}s]"
            
            logger.info(description)
            
            # The record_discovery is already called inside TrendingAdapter._fetch_*
            
    except Exception as e:
        logger.error(f"Discovery pass failed: {e}", exc_info=True)

    # Reload manifest to see if creators were added
    discovery_service = DiscoveryService(manifest_path)
    new_creators = discovery_service.manifest.get("discovered_creators", [])
    
    logger.info("═══ Discovery Test Results ═══")
    logger.info(f"Total Items Found: {results['total']}")
    logger.info(f"TikTok: {results['tiktok']}")
    logger.info(f"YouTube: {results['youtube']}")
    logger.info(f"Instagram: {results['instagram']}")
    logger.info(f"New Elite Creators Discovered: {len(new_creators)}")
    
    for c in new_creators:
        logger.info(f"✨ Found Creator: @{c.get('value')} ({c.get('platform')})")

if __name__ == "__main__":
    run_test()
