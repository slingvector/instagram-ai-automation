import os
import requests
import time
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Modern, Complete Emoji Database
EMOJI_DB_URL = "https://raw.githubusercontent.com/muan/emojilib/main/dist/emoji-en-US.json"
BASE_OUTPUT_DIR = "scripts/assets/packed_emojis"

# The High-Fidelity Source Tiering (Priority order)
SOURCES = [
    {
        "name": "Google_Noto_3D_512",
        "url": "https://fonts.gstatic.com/s/e/notoemoji/latest/{hex}/512.png",
        "hex_format": "standard"
    },
    {
        "name": "Fluent_3D",
        "url": "https://cdn.jsdelivr.net/gh/shuding/fluentui-emoji-unicode/assets/{hex}_3d.png",
        "hex_format": "standard"
    },
    {
        "name": "Noto_Color_128",
        "url": "https://raw.githubusercontent.com/googlefonts/noto-emoji/main/png/128/emoji_u{hex}.png",
        "hex_format": "underscore"
    }
]

def get_hex_codes(emoji_char: str) -> Dict[str, str]:
    """Generates various hex formats for different CDNs."""
    points = [f"{ord(c):x}" for c in emoji_char]
    if len(points) > 1:
        # Standard unicode normalization for CDNs often omits the FE0F selector
        points = [p for p in points if p != 'fe0f']
    
    return {
        "standard": "-".join(points),
        "underscore": "_".join(points)
    }

def download_single_emoji(char: str, category: str, description: str):
    """Downloads an emoji from the best available source."""
    safe_category = category.replace("/", "&").title()
    category_dir = os.path.join(BASE_OUTPUT_DIR, safe_category)
    os.makedirs(category_dir, exist_ok=True)
    
    hex_map = get_hex_codes(char)
    # We use standard-hex for the filename consistently
    final_path = os.path.join(category_dir, f"{hex_map['standard']}.png")
    
    # We check if it exists across any category to prevent duplicates
    # and to allow incremental harvesting
    if os.path.exists(final_path):
        return "skipped"

    for source in SOURCES:
        hex_code = hex_map[source["hex_format"]]
        url = source["url"].format(hex=hex_code)
        
        try:
            response = requests.get(url, stream=True, timeout=5)
            if response.status_code == 200:
                with open(final_path, "wb") as f:
                    for chunk in response.iter_content(4096):
                        f.write(chunk)
                return f"success ({source['name']})"
        except Exception:
            continue
            
    return "failed"

def harvest_emojis(limit: int = 0):
    logger.info("📥 Fetching Modern Emoji Database...")
    try:
        db_response = requests.get(EMOJI_DB_URL)
        emoji_data = db_response.json()
    except Exception as e:
        logger.error(f"Failed to fetch emoji DB: {e}")
        return

    # muan/emojilib is a dict {emoji: [tags]}
    items = []
    for char, tags in emoji_data.items():
        # Heuristic category if missing
        category = "Other"
        description = tags[0] if tags else "unknown"
        items.append((char, category, description))

    if limit > 0:
        items = items[:limit]

    total = len(items)
    logger.info(f"🚀 Starting High-Fidelity Harvest for {total} emojis...")
    
    success_count = 0
    fail_count = 0
    skipped_count = 0
    
    # Use 10 workers to be fast but respect rate limits
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(download_single_emoji, char, cat, desc): char for char, cat, desc in items}
        
        for future in as_completed(futures):
            result = future.result()
            if result == "skipped":
                skipped_count += 1
            elif "success" in result:
                success_count += 1
            else:
                fail_count += 1
                
    logger.info(f"🎉 Harvest Complete!")
    logger.info(f"   ✅ New: {success_count}")
    logger.info(f"   ⏩ Already Exists: {skipped_count}")
    logger.info(f"   ❌ Failed: {fail_count}")

if __name__ == "__main__":
    import sys
    # Allow passing limit as argument: python3 scripts/download_all_emojis.py 50
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    harvest_emojis(limit=limit)