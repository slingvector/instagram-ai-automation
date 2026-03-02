"""
src/ingestion/scheduler.py

Phase 6: The Master Ingestion Scheduler.
Runs the four SourceAdapters (DMs, Creator Watchlist, Trending Monitor, Cross-Platform)
at configured intervals using APScheduler.

Usage:
    python src/ingestion/scheduler.py
"""
import logging
import time
import os
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# Ensure we have our environment variables
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ingestion_scheduler")

# Import our four adapters
from src.ingestion.adapters.dm_adapter import DMAdapter
from src.ingestion.adapters.creator_adapter import CreatorAdapter
from src.ingestion.adapters.trending_adapter import TrendingAdapter
from src.ingestion.adapters.cross_platform_adapter import CrossPlatformAdapter

def execute_adapter(adapter_name: str, adapter_cls):
    """Generic wrapper to execute an adapter and log its output securely."""
    logger.info(f"=== Starting Scheduled Job: {adapter_name} ===")
    try:
        adapter = adapter_cls()
        items = adapter.fetch()
        
        if not items:
            logger.info(f"No new items yielded from {adapter_name}.")
            return
            
        logger.info(f"✅ Executed {adapter_name} - Fetched {len(items)} items to process queue.")
        # NOTE: At this stage in the pipeline roadmap, Downloader handles the raw download 
        # and the base MediaFactory handles B-roll overlay/GCS upload. Right now we are proving 
        # item extraction. We can hook downstream submission natively here in the future.
    except Exception as e:
        logger.exception(f"❌ Error during scheduled {adapter_name} execution: {e}")
    finally:
        logger.info(f"=== Finished Job: {adapter_name} ===")

def main():
    logger.info("Initializing MCR Ingestion Framework Scheduler...")
    
    # Optional debug setting: Run fast test intervals if DEV_MODE is 1
    dev_mode = os.getenv("DEV_MODE", "0") == "1"
    
    scheduler = BackgroundScheduler()
    
    if dev_mode:
        logger.warning("Starting in DEV_MODE - Intervals are compressed to minutes!")
        scheduler.add_job(lambda: execute_adapter("DM_Adapter", DMAdapter), 'interval', minutes=2)
        scheduler.add_job(lambda: execute_adapter("Trending_Adapter", TrendingAdapter), 'interval', minutes=1)
        scheduler.add_job(lambda: execute_adapter("Creator_Adapter", CreatorAdapter), 'interval', minutes=3)
        scheduler.add_job(lambda: execute_adapter("Cross_Platform", CrossPlatformAdapter), 'interval', minutes=4)
        
        # Trigger an immediate run in dev mode
        execute_adapter("Trending_Adapter (Initial)", TrendingAdapter)
    else:
        logger.info("Starting in PRODUCTION MODE")
        # Production intervals (as designed in architectural plan)
        scheduler.add_job(lambda: execute_adapter("DM_Adapter", DMAdapter), 'interval', minutes=20)
        scheduler.add_job(lambda: execute_adapter("Trending_Adapter", TrendingAdapter), 'interval', minutes=10)
        scheduler.add_job(lambda: execute_adapter("Creator_Adapter", CreatorAdapter), 'interval', hours=6)
        scheduler.add_job(lambda: execute_adapter("Cross_Platform", CrossPlatformAdapter), 'interval', hours=3)
        
        # Kick off the high-frequency tasks immediately on startup
        logger.info("Executing initial boot synchronization for fast-cadence sources...")
        execute_adapter("Trending_Adapter_Boot", TrendingAdapter)
        execute_adapter("DM_Adapter_Boot", DMAdapter)

    scheduler.start()
    logger.info("Scheduler is active (Press Ctrl+C to exit). Waiting for next tick...")

    try:
        # Keep the main thread alive so background threads continue executing
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down the scheduler gracefully...")
        scheduler.shutdown()
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    main()
