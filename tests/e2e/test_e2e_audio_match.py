"""
test_e2e_audio_match.py

Tests the Phase 7 Audio Matching logic.
Requires a physical device or emulator connected via ADB with Instagram installed
and logged in. This script simulates receiving an `audio_muted=True` flag
and ordering Appium to stitch a trending IG audio track over the video.
"""
import logging
import sys
import time

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("test_audio_match")

def main():
    logger.info("Starting Audio Matching Test in Appium...")
    
    from src.publishing_edge.services.appium_posting_service import AppiumPostingService
    
    # Needs a local test MP4 file on the device. Let's push one first.
    from src.publishing_edge.services.adb_client import ADBClient
    from src.publishing_edge.config import DEVICE_UDID
    
    adb = ADBClient(device_udid=DEVICE_UDID)
    
    # We'll use our fallback B-roll from Phase 5 as the test video
    local_test_video = "data/downloads/trending/trend_reddit_2.mp4"
    import os
    if not os.path.exists(local_test_video):
        logger.error(f"Test video not found: {local_test_video}. Please run the Phase 5 test first.")
        return
        
    logger.info(f"Pushing test video to device: {local_test_video}")
    device_path = adb.push_file(local_test_video, "/sdcard/Download/")
    logger.info(f"Pushed to: {device_path}")
    
    try:
        appium_service = AppiumPostingService()
        
        # Test Phase 7 Feature: needs_audio=True
        # This will trigger Step 4.5: _add_trending_audio()
        success = appium_service.prepare_reel_post(
            video_device_path=device_path,
            caption="Testing Phase 7 Auto-Audio Matching! 🎵🤖",
            needs_audio=True
        )
        
        if success:
            logger.info("✅ SUCCESS: Appium correctly navigated the IG Audio UI and staged the draft.")
        else:
            logger.error("❌ FAILED: Appium could not stage the draft with trending audio.")
            
    except Exception as e:
        logger.exception("❌ FAILED: Exception during Appium execution:")
        
    finally:
        # Clean up session
        if 'appium_service' in locals():
            appium_service.end_session()

if __name__ == "__main__":
    main()
