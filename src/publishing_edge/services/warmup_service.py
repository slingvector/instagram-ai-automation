import logging
import time
import random
from typing import Optional

from src.publishing_edge.services.adb_client import ADBClient
from src.publishing_edge.services.appium_posting_service import AppiumPostingService
from src.publishing_edge.config import DEVICE_UDID

logger = logging.getLogger(__name__)

class WarmupService:
    """
    Performs organic 'human-like' actions on the Instagram app (WRITE-ONLY account) 
    before posting a new Reel. This builds account trust and reduces shadowban risk.
    """
    def __init__(self):
        self._adb = ADBClient(device_udid=DEVICE_UDID)
        # Reuse the existing Appium infrastructure
        self._appium_service = AppiumPostingService()

    def perform_warmup(self, duration_minutes: int = 2) -> bool:
        """
        Wakes the device, launches IG, scrolls the home feed, and randomly likes posts
        or taps stories for the specified duration.
        """
        logger.info(f"Starting organic account warmup for {duration_minutes} minutes...")
        
        try:
            # 1. Start session and launch app
            self._appium_service.start_session()
            self._adb.unlock_device()
            self._adb.launch_instagram()
            time.sleep(8) # Wait for feed to load
            
            end_time = time.time() + (duration_minutes * 60)
            
            # Action loop
            while time.time() < end_time:
                action = random.choices(
                    ["scroll", "like", "pause"],
                    weights=[0.6, 0.2, 0.2]
                )[0]
                
                if action == "scroll":
                    self._human_scroll()
                elif action == "like":
                    self._human_like()
                elif action == "pause":
                    time.sleep(random.uniform(2.0, 5.0))
                    
            logger.info("✅ Account warmup completed successfully.")
            return True
            
        except Exception as e:
            logger.error(f"Account warmup failed: {e}")
            return False
        finally:
            # We don't end the session because the posting controller might need it immediately after
            pass

    def _human_scroll(self):
        """Perform a natural looking swipe."""
        start_y = random.randint(1800, 2200)
        end_y = random.randint(400, 800)
        start_x = random.randint(400, 800)
        # Small curve in the x-axis for 'humanity'
        end_x = start_x + random.randint(-100, 100)
        
        duration = random.randint(300, 800)
        self._adb.swipe(start_x, start_y, end_x, end_y, duration_ms=duration)
        time.sleep(random.uniform(1.0, 3.0))

    def _human_like(self):
        """Double tap the center of the screen to like a post."""
        logger.info("Mimicking human 'double tap' like on current post...")
        cx, cy = 720, 1400 # Approximate center of the screen image
        
        # Double tap via adb
        self._adb.tap(cx, cy)
        time.sleep(0.1)
        self._adb.tap(cx, cy)
        time.sleep(random.uniform(1.5, 3.5))
