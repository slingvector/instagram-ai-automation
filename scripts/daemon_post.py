"""
scripts/daemon_post.py

A lightweight daemon wrapper that endlessly executes the bulk_post pipeline
and sleeps between cycles. This prevents memory leaks by spinning up a fresh
process for each cycle.
"""
import time
import subprocess
import logging
import sys
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] daemon: %(message)s"
)
logger = logging.getLogger("daemon")

CYCLE_INTERVAL_SECONDS = int(os.getenv("DAEMON_INTERVAL_SECONDS", 3600)) # Default: 1 hour
REELS_PER_CYCLE = str(os.getenv("REELS_PER_CYCLE", "10"))
GAP_BETWEEN_REELS = str(os.getenv("GAP_BETWEEN_REELS", "180")) # 3 minutes
DISCOVERY_MANIFEST = os.getenv("DISCOVERY_MANIFEST", "config/hot_content_manifest.yaml")

def run_cycle():
    logger.info("🚀 Starting new bulk_post cycle...")
    try:
        cmd = [
            sys.executable, "scripts/bulk_post.py", 
            "--count", REELS_PER_CYCLE, 
            "--gap", GAP_BETWEEN_REELS,
            "--skip-preflight",
            "--config", DISCOVERY_MANIFEST
        ]
        # We run it synchronously and capture the output to stdout
        result = subprocess.run(cmd)
        if result.returncode == 0:
            logger.info("✅ Cycle completed successfully.")
        else:
            logger.error(f"❌ Cycle failed with exit code {result.returncode}.")
    except Exception as e:
        logger.exception(f"❌ Exception during cycle execution: {e}")

if __name__ == "__main__":
    logger.info(f"Starting Endless Cloud Daemon. Interval: {CYCLE_INTERVAL_SECONDS}s, Target: {REELS_PER_CYCLE} reels/cycle.")
    while True:
        run_cycle()
        logger.info(f"💤 Sleeping for {CYCLE_INTERVAL_SECONDS} seconds ({CYCLE_INTERVAL_SECONDS // 60} minutes)...")
        time.sleep(CYCLE_INTERVAL_SECONDS)
