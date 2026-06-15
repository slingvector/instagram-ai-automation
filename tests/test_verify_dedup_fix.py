import os
import sys
import sqlite3
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ingestion.dedup import canonical_url
from src.orchestration.state_manager import StateManager

def test_canonical_url():
    print("--- Testing canonical_url ---")
    urls = [
        "https://www.tiktok.com/@user/video/123?is_from_webapp=1&sender_device=pc",
        "https://www.tiktok.com/@user/video/123?tracking=abc",
        "https://www.tiktok.com/@user/video/123"
    ]
    canonical = {canonical_url(u) for u in urls}
    print(f"URLs: {urls}")
    print(f"Canonical set: {canonical}")
    assert len(canonical) == 1
    assert list(canonical)[0] == "https://www.tiktok.com/@user/video/123"
    print("✅ canonical_url works.")

def test_state_manager_dedup():
    print("\n--- Testing StateManager Dedup ---")
    db_path = "data/test_bulk_post_state.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    sm = StateManager(db_path=db_path)
    
    url1 = "https://www.youtube.com/watch?v=abc&t=10s"
    url2 = "https://www.youtube.com/watch?v=abc&feature=share"
    
    # 1. Add first URL
    added1 = sm.add_discovered_reel(url1, "Test Title", "youtube")
    print(f"Added url1: {added1}")
    assert added1 is True
    
    # 2. Add second URL (should be duplicate)
    added2 = sm.add_discovered_reel(url2, "Test Title", "youtube")
    print(f"Added url2: {added2}")
    assert added2 is False
    
    # 3. Verify only one entry exists
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM reel_states").fetchone()[0]
        print(f"Total entries in DB: {count}")
        assert count == 1
        
        db_url = conn.execute("SELECT url FROM reel_states").fetchone()[0]
        print(f"Stored URL: {db_url}")
        assert db_url == "https://www.youtube.com/watch?v=abc"
    
    os.remove(db_path)
    print("✅ StateManager deduplication with canonicalization works.")

if __name__ == "__main__":
    try:
        test_canonical_url()
        test_state_manager_dedup()
        print("\n🏆 Deduplication Fix Verification COMPLETE.")
    except Exception as e:
        print(f"\n❌ Verification FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
