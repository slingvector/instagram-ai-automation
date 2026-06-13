import os
import time
import logging
from src.media_factory.services.emoji_sprite_service import EmojiSpriteService

# Setup logging to see cache hits
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_cache_performance():
    cache_file = os.path.abspath("data/assets/sprite_map_cache.json")
    if os.path.exists(cache_file):
        os.remove(cache_file)
        print("🗑️  Cleaned old cache for cold-start test.")

    print("\n🏁 Test 1: Cold Start (Scanning Disk)...")
    start_time = time.time()
    service1 = EmojiSpriteService()
    cold_time = time.time() - start_time
    print(f"⏱️  Cold Start Time: {cold_time:.4f} seconds.")

    print("\n🏁 Test 2: Warm Start (Loading Cache)...")
    start_time = time.time()
    service2 = EmojiSpriteService()
    warm_time = time.time() - start_time
    print(f"⏱️  Warm Start Time: {warm_time:.4f} seconds.")

    improvement = (cold_time / warm_time) if warm_time > 0 else 0
    print(f"\n🚀 Performance Improvement: {improvement:.1f}x faster!")

    if warm_time < cold_time and os.path.exists(cache_file):
        print("✅ Cache Verification Passed!")
    else:
        print("❌ Cache Verification Failed!")

def test_tokenizer():
    service = EmojiSpriteService()
    pool = "vibe_success vibe_money vibe_energy"
    print(f"\n🏁 Test 3: Tokenizing Pool '{pool}'...")
    
    paths = service.get_sprites_for_pool(pool, count=5)
    print(f"📦 Resulting Paths: {len(paths)}")
    for i, p in enumerate(paths):
        print(f"  [{i+1}] {os.path.basename(p)}")

    if len(paths) == 5:
        print("✅ Tokenizer Padding Passed!")
    else:
        print("❌ Tokenizer Padding Failed!")

if __name__ == "__main__":
    test_cache_performance()
    test_tokenizer()
