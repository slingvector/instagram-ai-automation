"""
test_dm_scraper.py

Quick test for the DM adapter using the read-only IG account.
Runs in VISIBLE mode (headless=False) so you can see the browser
and manually solve any login challenges (CAPTCHA, 2FA, etc.).

Run:
    source venv/bin/activate
    python test_dm_scraper.py
"""
import logging
import os
import sys

# Load .env
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("test_dm_scraper")

# Verify credentials are loaded
username = os.environ.get("IG_READONLY_USERNAME", "")
password = os.environ.get("IG_READONLY_PASSWORD", "")
if not username or not password:
    logger.error("IG_READONLY_USERNAME / IG_READONLY_PASSWORD not set in .env")
    sys.exit(1)

logger.info(f"Testing DM scraper for @{username} ...")
logger.info("Browser will open in VISIBLE mode — handle any login prompts manually.")

from src.ingestion.adapters.dm_adapter import DMAdapter

# Run with headless=False so you can see exactly what's happening
adapter = DMAdapter(headless=False, max_threads=10)
items = adapter.fetch()

if not items:
    logger.info("No new Reel URLs found in DMs (inbox may be empty, or all already seen).")
else:
    logger.info(f"\n✅ Found {len(items)} new Reel(s) from DMs:\n")
    for i, item in enumerate(items, 1):
        logger.info(f"  {i}. {item.url}")
        logger.info(f"     platform={item.platform}, niche={item.niche}, account={item.target_account}")

logger.info("\nSQLite seen-ID DB updated — these messages won't be processed again.")
logger.info("Session cookies saved to: " + os.environ.get("IG_SESSION_FILE", "data/ig_readonly_session.json"))
