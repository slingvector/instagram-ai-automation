import os
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Premium 3D Emoji Mapping (Microsoft Fluent Design)
# Mapping: Emoji -> (Folder Name, File Name)
PREMIUM_EMOJIS = {
    "❤️": ("Heart", "heart_3d.png"),
    "🔥": ("Fire", "fire_3d.png"),
    "😂": ("Face with tears of joy", "face_with_tears_of_joy_3d.png"),
    "🙌": ("Raising hands", "raising_hands_3d.png"),
    "✨": ("Sparkles", "sparkles_3d.png"),
    "😍": ("Smiling face with heart-eyes", "smiling_face_with_heart-eyes_3d.png"),
    "💸": ("Money with wings", "money_with_wings_3d.png"),
    "🚀": ("Rocket", "rocket_3d.png"),
    "👏": ("Clapping hands", "clapping_hands_3d.png"),
    "💎": ("Gem stone", "gem_stone_3d.png"),
    "✅": ("Check mark button", "check_mark_button_3d.png"),
    "💯": ("Hundred points", "hundred_points_3d.png"),
    "🎉": ("Party popper", "party_popper_3d.png"),
    "🤯": ("Exploding head", "exploding_head_3d.png"),
    "⚡": ("High voltage", "high_voltage_3d.png")
}

BASE_URL = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets"
ASSET_DIR = "data/assets/emojis_3d"

def download_premium_emoji(char, folder, filename):
    # Encode folder name for URL (e.g., Space to %20)
    encoded_folder = folder.replace(" ", "%20")
    url = f"{BASE_URL}/{encoded_folder}/3D/{filename}"
    target_path = os.path.join(ASSET_DIR, f"{char}.png")
    
    if os.path.exists(target_path):
        return
        
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            with open(target_path, "wb") as f:
                f.write(response.content)
            logger.info(f"✅ Downloaded 3D sprite for {char} ({folder})")
        else:
            logger.warning(f"❌ Failed to download {char} from {url} (Status: {response.status_code})")
            # Try fallback to 'emoji_3d.png' if filename guess was wrong
            fallback_url = f"{BASE_URL}/{encoded_folder}/3D/emoji_3d.png"
            resp2 = requests.get(fallback_url, timeout=10)
            if resp2.status_code == 200:
                with open(target_path, "wb") as f:
                    f.write(resp2.content)
                logger.info(f"✅ Downloaded 3D sprite for {char} via fallback URL")
    except Exception as e:
        logger.error(f"Error downloading {char}: {e}")

if __name__ == "__main__":
    os.makedirs(ASSET_DIR, exist_ok=True)
    logger.info(f"🚀 Upgrading to High-Fidelity 3D Emojis...")
    for char, (folder, filename) in PREMIUM_EMOJIS.items():
        download_premium_emoji(char, folder, filename)
    logger.info("✨ Premium asset setup complete.")
