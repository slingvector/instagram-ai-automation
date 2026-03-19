import os
import sys
import logging
import time
from dotenv import load_dotenv

# Ensure we can import from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("world_test_v2")

from src.orchestration.state_manager import StateManager, ReelState
from tests.bulk_post import BulkPosterStateMachine

def run_world_test():
    logger.info("🌍 Starting Emoji Engine v2.0 World Test Audit...")
    
    sm = StateManager()
    pending = sm.get_pending_reels()
    
    # Filter for reels that are DOWNLOADED but not processed or partially processed
    # We want a fresh one to test the full v2.0 logic from scratch
    eligible = [r for r in pending if r['state'] == ReelState.DOWNLOADED]
    
    if not eligible:
        logger.error("❌ No eligible DOWNLOADED reels found in state manager.")
        return

    # Pick the oldest one
    target_reel = eligible[0]
    logger.info(f"🎯 Target Reel Selected: {target_reel['title']} (URL: {target_reel['url']})")

    # Initialize the state machine
    poster = BulkPosterStateMachine()
    
    logger.info("🚀 Executing single-reel production pipeline with v2.0 logic...")
    
    # Force reset state to DISCOVERED to ensure fresh re-processing
    url = target_reel['url']
    sm.update_state(url, ReelState.DISCOVERED)
    target_reel['state'] = ReelState.DISCOVERED
    target_reel['gcs_uri'] = None 

    # Process only this one reel
    try:
        # We use the state machine but force a high-fidelity vibe
        # BulkPosterStateMachine will handle the transitions
        # We'll monkey-patch the style selection if needed, but let's try standard first
        wait_time = poster._process_single_reel(target_reel, tag="[WORLD-TEST-V2]")
        
        if wait_time > 0:
            logger.info(f"✅ World Test: Pipeline completed successfully for {url}.")
            logger.info("👉 Please verify the post on Instagram for: Beat-Sync, 3D Assets, and Sentiment Physics.")
        else:
            logger.warning(f"⚠️ World Test: Processing finished but reel {url} was marked irrelevant or failed.")
            
    except Exception as e:
        logger.error(f"❌ World Test FATAL: {url} failed with error: {e}", exc_info=True)
        # Optionally reset back to DISCOVERED so it can be retried manually
        sm.update_state(url, ReelState.FAILED, error_message=str(e))

if __name__ == "__main__":
    run_world_test()
