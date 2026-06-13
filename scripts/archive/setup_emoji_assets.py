import os
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Essential Instagram/Story Emojis
EMOJI_LIST = {
    "❤️": "2764",
    "🔥": "1f525",
    "😂": "1f602",
    "🙌": "1f64c",
    "✨": "2728",
    "😍": "1f60d",
    "💸": "1f4b8",
    "🚀": "1f680",
    "👏": "1f44f",
    "💎": "1f48e",
    "✅": "2705"
}

ASSET_DIR = "data/assets/emojis"

def download_twemoji(char, code):
    url = f"https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/72x72/{code}.png"
    target_path = os.path.join(ASSET_DIR, f"{code}.png")
    
    if os.path.exists(target_path):
        return
        
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            with open(target_path, "wb") as f:
                f.write(response.content)
            logger.info(f"Downloaded sprite for {char} ({code})")
        else:
            logger.error(f"Failed to download {char} from {url}")
    except Exception as e:
        logger.error(f"Error downloading {char}: {e}")

if __name__ == "__main__":
    os.makedirs(ASSET_DIR, exist_ok=True)
    logger.info(f"Downloading {len(EMOJI_LIST)} emoji sprites to {ASSET_DIR}...")
    for char, code in EMOJI_LIST.items():
        download_twemoji(char, code)
    logger.info("Emoji asset setup complete.")
