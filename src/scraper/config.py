import os
from dotenv import load_dotenv
from pathlib import Path

from src.config import GCP_PROJECT_ID, GCS_BUCKET_RAW as GCS_BUCKET_NAME, GOOGLE_APPLICATION_CREDENTIALS

# Load environment variables from .env file
load_dotenv()

# Directories
BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "scraped_reels.db"
USER_DATA_DIR = DATA_DIR / "browser_session"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Scraper Configuration
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
TARGET_INSTAGRAM_CHAT_URL = os.getenv("TARGET_INSTAGRAM_CHAT_URL", "https://www.instagram.com/direct/inbox/")
PROXY_SERVER = os.getenv("PROXY_SERVER", None)
HEADLESS = os.getenv("HEADLESS", "False").lower() == "true"

