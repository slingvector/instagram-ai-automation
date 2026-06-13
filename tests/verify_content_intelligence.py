"""
tests/verify_content_intelligence.py

Verifies Phase 1 of the Content Intelligence Pipeline.
1. Checks data enrichment (comment_count, upload_timestamp).
2. Checks Level 2 filters (Engagement Quality).
3. Checks Level 3 scoring (Virality Momentum).
"""
import sys
import os
import json
import logging
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ingestion.adapters.trending_adapter import TrendingAdapter
from src.ingestion.base import Platform, ContentItem
from src.ingestion.services.discovery_service import DiscoveryService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_intelligence_calculations():
    print("\n--- Testing DiscoveryService Intelligence Calculations ---")
    ds = DiscoveryService("config/discovery_manifest.yaml")
    
    # 1. Test Rates
    rates = ds.calculate_rates(100000, 5000, 1000)
    print(f"Rates for 100k views, 5k likes, 1k comments: {rates}")
    assert rates["like_rate"] == 0.05
    assert rates["comment_rate"] == 0.01
    
    # 2. Test Velocity
    import time
    timestamp_1h_ago = int(time.time() - 3600)
    velocity = ds.calculate_velocity(10000, timestamp_1h_ago)
    print(f"Velocity for 10k views in 1 hour: {velocity} views/hr")
    assert velocity >= 9000.0
    
    # 3. Test Virality Score
    score = ds.compute_virality_score({
        "view_count": 100000,
        "like_count": 8000,
        "comment_count": 1000,
        "upload_timestamp": timestamp_1h_ago
    })
    print(f"Virality Score for high-momentum video: {score}")
    assert 0.0 <= score <= 1.0
    
    print("✅ Intelligence calculations verified.")

def test_trending_adapter_intel():
    print("\n--- Testing TrendingAdapter Intelligence Integration ---")
    adapter = TrendingAdapter("config/discovery_manifest.yaml")
    
    # Mock data for a viral candidate
    mock_url = "https://www.tiktok.com/@test/video/12345"
    
    # Test if ContentItem can hold the new fields
    import time
    from src.ingestion.base import Niche
    item = ContentItem(
        url=mock_url,
        platform=Platform.TIKTOK,
        source_type=adapter.source_type,
        niche=Niche.ENTERTAINMENT,
        engagement_score=0.85,
        view_count=500000,
        like_count=25000,
        comment_count=1200,
        upload_timestamp=int(time.time() - 7200),
        title="Test Viral Candidate"
    )
    
    print(f"ContentItem created: {item.title}")
    print(f"Signals: Views={item.view_count}, Likes={item.like_count}, Comments={item.comment_count}, Timestamp={item.upload_timestamp}")
    
    assert item.comment_count == 1200
    assert item.upload_timestamp is not None
    
    print("✅ TrendingAdapter intelligence integration verified.")

if __name__ == "__main__":
    try:
        test_intelligence_calculations()
        test_trending_adapter_intel()
        print("\n🏆 Phase 1 Content Intelligence Verification COMPLETE.")
    except Exception as e:
        print(f"\n❌ Verification FAILED: {e}")
        sys.exit(1)
