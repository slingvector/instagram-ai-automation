import logging
import os
from src.media_factory.services.emoji_sprite_service import EmojiSpriteService

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_semantic_mapping():
    service = EmojiSpriteService()
    
    test_queries = [
        ("vibe_money", "Hero Vibe (Money)"),
        ("vibe_success", "Hero Vibe (Success)"),
        ("vibe_nature", "Hero Vibe (Nature)"),
        ("vibe_luxury", "Hero Vibe (Luxury)"),
        ("vibe_travel", "Hero Vibe (Travel)"),
        ("vibe_pizza", "Dynamic Keyword (Pizza)"),
        ("vibe_car", "Dynamic Keyword (Car)"),
        ("vibe_mountain", "Dynamic Keyword (Mountain)"),
        ("1f680", "Direct Hex (Rocket)"),
        ("🔥", "Direct Char (Fire)"),
        ("invalid_vibe_tag", "Invalid Tag (Fallback expected)"),
        ("unknown_char_XYZ", "Unknown String (Fallback expected)")
    ]
    
    print("\n--- Emoji Asset-First Mapping Test ---")
    success_count = 0
    
    for query, desc in test_queries:
        path = service.get_sprite_path(query)
        if path:
            print(f"✅ {desc} [{query}]:")
            print(f"   Path: {os.path.relpath(path)}")
            success_count += 1
        else:
            print(f"❌ {desc} [{query}]: FAILED")
            
    print(f"\nResults: {success_count}/{len(test_queries)} queries resolved.")
    
    # Verify fallback for invalid tag is '2728' (Sparkles)
    fallback_path = service.get_sprite_path("this_tag_does_not_exist")
    if fallback_path and "2728" in fallback_path:
        print("✅ Fallback logic working correctly (Sparkles).")
    else:
        print("❌ Fallback logic FAILED.")

if __name__ == "__main__":
    test_semantic_mapping()
