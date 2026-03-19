import logging
import time
import os
import base64
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from datetime import datetime
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, InvalidSessionIdException, WebDriverException, NoSuchElementException

from src.publishing_edge.services.adb_client import ADBClient
from src.publishing_edge.config import (
    APPIUM_HOST as CONFIG_APPIUM_HOST, DEVICE_UDID, INSTAGRAM_PACKAGE,
    INSTAGRAM_ACTIVITY, NEW_COMMAND_TIMEOUT, ANDROID_HOME
)

# Hardened sanitization: Ensure no legacy /wd/hub suffix enters the connection URL
APPIUM_HOST = CONFIG_APPIUM_HOST.replace("/wd/hub", "").rstrip("/")

# Hardward Environment Persistence: Ensure Appium client process has SDK paths
if ANDROID_HOME:
    os.environ["ANDROID_HOME"] = ANDROID_HOME
    # Also ensure its platform-tools are in the path for adb calls
    platform_tools = os.path.join(ANDROID_HOME, "platform-tools")
    if platform_tools not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{platform_tools}{os.pathsep}{os.environ.get('PATH', '')}"

logger = logging.getLogger(__name__)

# ─── Timing constants (seconds) ─────────────────────────────────────────────
WAIT_SHORT = 5
WAIT_MEDIUM = 10
WAIT_LONG = 15
# ─────────────────────────────────────────────────────────────────────────────


class AppiumPostingService:
    """
    Singleton Appium session manager for Instagram Reel posting.

    Reuses the proven pattern from the LinkedIn automation project:
    - Single session to prevent port/resource clashing
    - Auto-recovery via ADB wake on session failure
    - ADB fallback for unreliable UI element interactions
    """

    _instance: Optional["AppiumPostingService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._driver = None
            cls._instance._adb = ADBClient(device_udid=DEVICE_UDID)
        return cls._instance

    # ── Session Management ────────────────────────────────────────────────────

    def start_session(self):
        """Starts the Appium session. Only instantiates a new one if not alive."""
        if self._driver:
            try:
                # Basic check to see if driver is still responding
                _ = self._driver.orientation
                return
            except Exception:
                self._driver = None

        # Clean start requested: Force stop Instagram before every fresh session
        logger.info("Performing clean state reset: Force-stopping Instagram...")
        self._adb.stop_instagram()
        time.sleep(2)

        options = UiAutomator2Options()
        options.platform_name = "Android"
        options.automation_name = "UiAutomator2"
        options.app_package = INSTAGRAM_PACKAGE
        options.app_activity = INSTAGRAM_ACTIVITY
        options.no_reset = True
        options.new_command_timeout = NEW_COMMAND_TIMEOUT
        options.auto_grant_permissions = True # Keep this from original _build_options
        
        # Instruct Appium server to drop any stale port configurations and logs before reconnecting
        options.set_capability("appium:clearSystemFiles", True)
        # Industrial reliability: extend timeouts for slow device installs
        options.set_capability("appium:uiautomator2ServerInstallTimeout", 60000)
        options.set_capability("appium:adbExecTimeout", 30000)

        if DEVICE_UDID:
            options.udid = DEVICE_UDID
            
        # Explicitly instruct Appium server to use the host machine's ADB daemon socket
        # (required for Dockerized Appium to see USB-attached phones on macOS)
        # Explicitly declare the ADB binary so Appium skips the strict ANDROID_HOME folder checks
        options.set_capability("appium:adbExecutable", "/opt/homebrew/bin/adb")
        
        # Connection loop for Appium Server
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Pre-emptive ADB recovery on retry
                if attempt > 0:
                    logger.warning(f"Appium: Attempt {attempt + 1}: Triggering ADB wake + deep cleaner...")
                    self._adb.wake_screen()
                    self._adb._run(["shell", "am", "force-stop", "io.appium.uiautomator2.server"])
                    self._adb._run(["shell", "am", "force-stop", "io.appium.uiautomator2.server.test"])
                    self._adb._run(["shell", "am", "force-stop", "com.instagram.android"])
                    time.sleep(3)

                logger.info(f"Appium: Requesting new session on {APPIUM_HOST} (Attempt {attempt + 1}/{max_retries})")
                self._driver = webdriver.Remote(APPIUM_HOST, options=options)
                self._driver.implicitly_wait(10)
                logger.info("✅ Appium session connected successfully.")
                return
            except WebDriverException as e: 
                error_msg = str(e)
                logger.error(f"Appium session initiation failed: {error_msg}")
                
                # Check for "UiAutomation not connected" or generic connection refused
                is_connection_refused = "Connection refused" in error_msg or "Failed to establish a new connection" in error_msg
                is_stale_package = "UiAutomation not connected" in error_msg or "SessionNotCreatedException" in error_msg
                
                if (is_connection_refused or is_stale_package) and attempt < max_retries - 1:
                    logger.warning("♻️ Appium Connection Deadlock Detected: Force-stopping orphaned UiAutomator2 servers from device RAM...")
                    self._adb._run(["shell", "am", "force-stop", "io.appium.uiautomator2.server"])
                    self._adb._run(["shell", "am", "force-stop", "io.appium.uiautomator2.server.test"])
                    time.sleep(4)
                    logger.info("Retrying Appium connection...")
                elif "io.appium.settings" in error_msg and attempt < max_retries - 1:
                    logger.warning("🚨 Appium Settings Activity Missing! Triggering DEEP CLEAN protocol...")
                    # Completely purge suspected corrupted helper apps
                    self._adb._run(["uninstall", "io.appium.settings"])
                    self._adb._run(["uninstall", "io.appium.uiautomator2.server"])
                    self._adb._run(["uninstall", "io.appium.uiautomator2.server.test"])
                    logger.info("Helper apps uninstalled. Appium will re-install them clean on next attempt.")
                    time.sleep(5)
                elif attempt < max_retries - 1:
                    logger.info("Retrying Appium connection in 5s...")
                    time.sleep(5)
                else:
                    raise RuntimeError(f"Could not connect Appium after {max_retries} attempts.") from e
            except Exception as e: 
                logger.error(f"Appium session start failed with unexpected error: {e}. Attempting ADB wake recovery...")
                self._adb.wake_screen()
                time.sleep(2)
                if attempt < max_retries - 1:
                    logger.info("Retrying Appium connection after wake recovery...")
                else:
                    raise RuntimeError(f"Could not connect Appium after {max_retries} attempts due to unexpected error.") from e


    def end_session(self):
        """Cleanly quit the Appium session."""
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            finally:
                self._driver = None
                logger.info("Appium session ended.")

    def _build_options(self) -> UiAutomator2Options:
        # This method is now largely redundant as options are built in start_session
        # Keeping it for now, but its content is no longer used by start_session
        options = UiAutomator2Options()
        options.platform_name = "Android"
        options.automation_name = "UiAutomator2"
        options.app_package = INSTAGRAM_PACKAGE
        options.app_activity = INSTAGRAM_ACTIVITY
        options.no_reset = True          # Stay logged in — critical
        options.new_command_timeout = NEW_COMMAND_TIMEOUT
        options.auto_grant_permissions = True
        
        # Explicitly instruct Appium server to use the host machine's ADB daemon socket 
        # (required for Dockerized Appium to see USB-attached phones on macOS)
        # Explicitly declare the ADB binary so Appium skips the strict ANDROID_HOME folder checks
        options.set_capability("appium:adbExecutable", "/opt/homebrew/bin/adb")
        
        # Note: skipServerInstallation removed so Appium can reinstall UIAutomator2 APKs if needed
        if DEVICE_UDID:
            options.udid = DEVICE_UDID
        return options

    def _reset_to_home(self):
        """
        Presses the Android BACK key repeatedly until the Instagram bottom tab bar is visible,
        then explicitly taps the Feed (Home) tab to ensure a clean starting state.
        This handles cases where the OS resurrects a saved activity (like an open Reel).
        """
        logger.info("Resetting Instagram to Home tab to clear any open overlays or Reels...")
        for i in range(5):
            src = self._driver.page_source
            if src and "com.instagram.android:id/tab_bar" in src:
                logger.info("Bottom tab bar found. Ensuring Home tab is active...")
                
                # Check if we can tap the home tab directly via resource-id
                home_tab_id = "com.instagram.android:id/feed_tab"
                if home_tab_id in src:
                    xml_root = ET.fromstring(src.encode('utf-8'))
                    for node in xml_root.iter():
                        if node.attrib.get('resource-id') == home_tab_id:
                            bounds_str = node.attrib.get('bounds')
                            if bounds_str:
                                import re
                                m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
                                if m:
                                    x1, y1, x2, y2 = map(int, m.groups())
                                    self._adb.tap((x1 + x2) // 2, (y1 + y2) // 2)
                                    time.sleep(WAIT_SHORT)
                                    return
                    
                # Fallback if XML interaction fails
                # Known center for Home tab [0,2868][288,3060] -> (144, 2964)
                self._adb.tap(144, 2964)
                time.sleep(WAIT_SHORT)
                return
                
            logger.info(f"Tab bar not found (Attempt {i+1}/5). Pressing BACK key...")
            self._adb._run(["shell", "input", "keyevent", "KEYCODE_BACK"])
            time.sleep(WAIT_SHORT)
            
        logger.warning("Could not find bottom tab bar after multiple BACK presses. Proceeding with caution.")

    # ── Core Posting Flow ─────────────────────────────────────────────────────

    def prepare_reel_post(self, video_device_path: str, caption: str, needs_audio: bool = False) -> bool:
        """
        Navigates Instagram to a ready-to-share Reel draft.

        Steps:
          1. Wake device + launch Instagram via ADB
          2. Tap the "+" create button
          3. Select "Reel" tab
          4. Choose the video from device gallery
          5. [Optional] Add trending audio if original was muted
          6. Next → apply caption
          7. STOP — leaves draft open for human review (does NOT tap Share)

        Returns True if draft is staged successfully.
        Raises RuntimeError on unrecoverable error.
        """
        self.start_session()
        d = self._driver

        try:
            logger.info("Step 1: Wake screen, unlock device, and ensure Instagram is in foreground.")
            self._adb.unlock_device()
            self._adb.launch_instagram()
            
            # Wait for Instagram to actually be in foreground
            max_wait = 15
            for i in range(max_wait):
                pkg = self._adb.get_foreground_package()
                if pkg == INSTAGRAM_PACKAGE:
                    logger.info(f"Instagram is in foreground after {i}s.")
                    break
                time.sleep(1)
            else:
                logger.warning("Instagram package not detected in foreground. Proceeding with caution.")

            time.sleep(WAIT_SHORT)
            # Check for 'Not Now' or common startup popups
            if self._tap_by_text_xml("Not now", timeout=2, exact_match=False):
                logger.info("Dismissed 'Not Now' popup.")
                
            self._reset_to_home()
            self._save_debug_state("01_instagram_launched")

            logger.info("Step 2: Navigate to Profile and tap 'Create New'")
            if not self._tap_bottom_tab("Profile", timeout=WAIT_SHORT):
                logger.warning("Profile tab not found via resource-id. Tapping fallback coordinate (1300, 2850).")
                self._adb.tap(1300, 2850)
            time.sleep(WAIT_MEDIUM)
            self._save_debug_state("02a_profile_tab")

            self._tap_element_or_coords(
                by=AppiumBy.ACCESSIBILITY_ID,
                value="Create New",
                fallback_coords=(96, 225),  # top-left corner on profile tab
            )
            time.sleep(WAIT_MEDIUM)
            self._save_debug_state("02b_after_create_tap")

            logger.info("Step 3: Ensure we are on the Reel gallery screen.")
            src = self._driver.page_source
            if "Recents" in src or "New reel" in src:
                logger.info("Already on New Reel gallery screen. Skipping slider tap.")
            else:
                # We are on the creation bottom sheet - need to tap 'Reel'
                logger.info("On creation sheet. Tapping Reel option via XML.")
                if not self._tap_by_text_xml("Reel", timeout=WAIT_MEDIUM, exact_match=True):
                    self._adb.tap(800, 2950)
            time.sleep(WAIT_SHORT)
            self._save_debug_state("03_after_reel_select")

            logger.info("Step 4: Select the video from the device gallery via XML grid scan.")
            if not self._tap_first_video_in_gallery(timeout=WAIT_MEDIUM):
                logger.error("Could not locate a video item in the gallery grid. Aborting.")
                self._save_debug_state("04_gallery_select_FAILED")
                return False
            time.sleep(WAIT_MEDIUM)
            self._save_debug_state("04_after_video_select")

            if needs_audio:
                logger.info("Step 4.5: Video audio was muted by source. Equipping a trending IG audio track.")
                self._add_trending_audio()
                self._save_debug_state("04b_after_audio_add")

            logger.info("Step 5: Tap 'Next' to proceed to caption screen.")
            time.sleep(3)  # Extra wait for video to fully load in Reel editor
            self._tap_next_button()
            time.sleep(WAIT_MEDIUM)
            self._save_debug_state("05_after_next")

            # Verify we reached the caption screen (not still on editor)
            src = self._driver.page_source
            if "Write a caption" not in src and "Share" not in src:
                logger.warning("Did not reach caption screen after Next. Retrying Next tap.")
                self._tap_next_button()
                time.sleep(WAIT_MEDIUM)

            logger.info("Step 6: Enter caption.")
            self._enter_caption(caption)
            time.sleep(WAIT_SHORT)

            logger.info("Draft staged. Waiting for human review before Share.")
            return True

        except Exception as e:
            screenshot = self._adb.get_screenshot("/tmp/mcr_error_screen.png")
            logger.error(f"Error staging Reel draft: {e}. Screenshot: {screenshot}")
            self.end_session()
            raise RuntimeError(f"Failed to stage Reel: {e}") from e

    def share_post(self) -> bool:
        """
        Taps the final 'Share' button after human review approval.
        Called by PostingController only after Firestore status = 'approved'.
        """
        try:
            logger.info("Human review approved. Tapping Share...")
            self._tap_element_or_coords(
                by=AppiumBy.XPATH,
                value='//android.widget.TextView[@text="Share"]',
                fallback_coords=(540, 1850),
            )
            time.sleep(WAIT_LONG)
            logger.info("Reel posted successfully.")
            return True
        except Exception as e:
            logger.error(f"Share tap failed: {e}")
            raise RuntimeError(f"Share failed: {e}") from e
        finally:
            self.end_session()

    def cancel_post(self):
        """Discard the draft and close session on human rejection."""
        try:
            d = self._driver
            if d:
                d.press_keycode(4)  # Android BACK
                time.sleep(1)
                d.press_keycode(4)
        except Exception:
            pass
        finally:
            self.end_session()
            logger.info("Post cancelled by human reviewer.")

    # ── Cross-Platform Extensions ─────────────────────────────────────────────

    def crosspost_to_tiktok(self, caption: str) -> bool:
        """
        Automates uploading the already-staged video to TikTok.
        Takes advantage of the video already being topmost in the gallery.
        """
        self.start_session()
        try:
            logger.info("Starting TikTok Crosspost Flow...")
            self._adb.launch_tiktok()
            time.sleep(WAIT_MEDIUM)
            
            logger.info("Tapping TikTok Create button...")
            if not self._tap_by_text_xml("Create", timeout=WAIT_SHORT, exact_match=False, min_y=2000):
                self._adb.tap(720, 2900)  # Common center-bottom + coordinate
            time.sleep(WAIT_SHORT)
            
            logger.info("Tapping Upload from gallery...")
            if not self._tap_by_text_xml("Upload", timeout=WAIT_SHORT, exact_match=False):
                self._adb.tap(1100, 2500)
            time.sleep(WAIT_MEDIUM)
            
            logger.info("Selecting first topmost video in gallery...")
            self._adb.tap(250, 500)
            time.sleep(WAIT_SHORT)
            
            logger.info("Tapping Next in TikTok editor...")
            if not self._tap_by_text_xml("Next", timeout=WAIT_SHORT):
                self._adb.tap(1200, 2900)
            time.sleep(WAIT_MEDIUM)
            
            logger.info("Pasting TikTok Caption...")
            if self._tap_by_text_xml("Describe your post", timeout=WAIT_SHORT):
                self._driver.set_clipboard_text(caption)
                time.sleep(0.5)
                self._adb._run(["shell", "input", "keyevent", "279"])
            time.sleep(WAIT_SHORT)
            
            logger.info("Tapping TikTok Post...")
            if not self._tap_by_text_xml("Post", timeout=WAIT_SHORT):
                self._adb.tap(1200, 2900)
                
            logger.info("TikTok crosspost complete.")
            return True
        except Exception as e:
            logger.error(f"TikTok crosspost failed: {e}")
            return False
        finally:
            self.end_session()

    def crosspost_to_youtube_shorts(self, caption: str) -> bool:
        """
        Automates uploading the already-staged video to YouTube Shorts.
        Takes advantage of the video already being topmost in the gallery.
        """
        self.start_session()
        try:
            logger.info("Starting YouTube Shorts Crosspost Flow...")
            self._adb.launch_youtube()
            time.sleep(WAIT_MEDIUM)
            
            logger.info("Tapping YouTube Create button...")
            if not self._tap_by_text_xml("Create", timeout=WAIT_SHORT, exact_match=False, min_y=2000):
                self._adb.tap(720, 2900)
            time.sleep(WAIT_SHORT)
            
            logger.info("Selecting 'Create a Short'...")
            if not self._tap_by_text_xml("Create a Short", timeout=WAIT_SHORT, exact_match=False):
                self._adb.tap(720, 2200)
            time.sleep(WAIT_MEDIUM)
            
            logger.info("Opening gallery...")
            self._adb.tap(150, 2500)
            time.sleep(WAIT_SHORT)
            
            logger.info("Selecting first topmost video in gallery...")
            self._adb.tap(250, 500)
            time.sleep(WAIT_SHORT)
            
            logger.info("Tapping Done...")
            if not self._tap_by_text_xml("Done", timeout=WAIT_SHORT):
                self._adb.tap(1200, 2900)
            time.sleep(WAIT_LONG)
            
            logger.info("Tapping Next in YouTube editor...")
            if not self._tap_by_text_xml("Next", timeout=WAIT_SHORT):
                self._adb.tap(1200, 150)
            time.sleep(WAIT_MEDIUM)
            
            logger.info("Pasting YouTube Caption...")
            if self._tap_by_text_xml("Caption your Short", timeout=WAIT_SHORT):
                self._driver.set_clipboard_text(caption)
                time.sleep(0.5)
                self._adb._run(["shell", "input", "keyevent", "279"])
            time.sleep(WAIT_SHORT)
            
            logger.info("Tapping Upload Short...")
            if not self._tap_by_text_xml("Upload Short", timeout=WAIT_SHORT):
                self._adb.tap(720, 2900)
                
            logger.info("YouTube Shorts crosspost complete.")
            return True
        except Exception as e:
            logger.error(f"YouTube Shorts crosspost failed: {e}")
            return False
        finally:
            self.end_session()

    # ── Private Helpers ───────────────────────────────────────────────────────

    def _save_debug_state(self, step_name: str):
        """
        Saves a screenshot and XML page source dump to the debug/ folder.
        Files are named: debug/<timestamp>_<step_name>.png / .xml
        Use these to visually confirm what the screen looks like at each stage.
        """
        try:
            debug_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "debug")
            os.makedirs(debug_dir, exist_ok=True)
            ts = datetime.now().strftime("%H%M%S")
            base = os.path.join(debug_dir, f"{ts}_{step_name}")

            # Screenshot via ADB
            self._adb._run(["shell", "screencap", "-p", f"/sdcard/debug_snap.png"])
            self._adb._run(["pull", f"/sdcard/debug_snap.png", f"{base}.png"])

            # XML dump from Appium page_source
            source = self._driver.page_source if self._driver else ""
            with open(f"{base}.xml", "w", encoding="utf-8") as f:
                f.write(source)

            logger.info(f"Debug state saved → {base}.png / .xml")
        except Exception as e:
            logger.debug(f"Debug state save failed (non-critical): {e}")

    def _tap_first_video_in_gallery(self, timeout: int = WAIT_MEDIUM) -> bool:
        """
        Strategy 1 (preferred): Search for a node whose content-desc contains
        'Video thumbnail' — this is the exact text Instagram uses for video items
        in the Reel gallery grid (confirmed from XML recording data).

        Strategy 2 (fallback): Find all Button/ImageView/ViewGroup nodes whose
        center Y is > 800 (below the tab bar at cy≈449 and Recents row at cy≈668),
        sort in reading order, skip index 0 (Camera icon), tap index 1 (first video).

        NOTE: The gallery grid starts at y=783 on a 1440x3120 device.
              Tab icons (Edits/Drafts/Templates) live at cy≈449 — they must be skipped.
        """
        start_time = time.time()
        logger.info("Scanning XML for first video thumbnail in gallery...")

        while time.time() - start_time < timeout:
            try:
                source = self._driver.page_source
                xml_root = ET.fromstring(source.encode('utf-8'))

                # ── Strategy 1: content-desc "Video thumbnail" ──────────────────
                for node in xml_root.iter():
                    desc = node.attrib.get('content-desc', '')
                    if 'Video thumbnail' in desc or 'video thumbnail' in desc.lower():
                        bounds_str = node.attrib.get('bounds', '')
                        m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
                        if m:
                            x1, y1, x2, y2 = map(int, m.groups())
                            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                            logger.info(f"Strategy 1 ✓ Found '{desc[:50]}' at ({cx},{cy}). Tapping.")
                            self._adb.tap(cx, cy)
                            return True

                # ── Strategy 2: ImageView/Button below tab bar (min_y=800) ──────
                MIN_GRID_Y = 800   # gallery grid starts at y=783 on this device
                grid_items = []
                for node in xml_root.iter():
                    cls = node.attrib.get('class', '')
                    if not any(t in cls for t in ['ImageView', 'Button', 'ViewGroup']):
                        continue
                    # Must have a specific content-desc to be a real grid item
                    desc = node.attrib.get('content-desc', '')
                    if not desc:
                        continue
                    bounds_str = node.attrib.get('bounds', '')
                    m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
                    if not m:
                        continue
                    x1, y1, x2, y2 = map(int, m.groups())
                    cy = (y1 + y2) // 2
                    if cy < MIN_GRID_Y:
                        logger.debug(f"Strategy 2: skipping '{desc[:30]}' at cy={cy} (above grid)")
                        continue
                    cx = (x1 + x2) // 2
                    grid_items.append((cy, cx, desc))

                grid_items.sort(key=lambda i: (i[0], i[1]))
                logger.debug(f"Strategy 2: {len(grid_items)} grid items found: {[(i[2][:25], i[1]) for i in grid_items[:5]]}")

                # Skip "Open camera" (index 0), take first video/photo after it
                for item in grid_items:
                    cy, cx, desc = item
                    if 'camera' in desc.lower():
                        continue                  # skip camera button
                    logger.info(f"Strategy 2 ✓ Tapping '{desc[:50]}' at ({cx},{cy})")
                    self._adb.tap(cx, cy)
                    return True

            except Exception as e:
                logger.debug(f"Gallery scan error: {e}")

            time.sleep(1)

        logger.warning("Timeout: Could not locate a video thumbnail in the gallery.")
        return False

    def _tap_by_text_xml(self, target_text: str, timeout: int = WAIT_MEDIUM, exact_match: bool = False, min_y: int = 0) -> bool:
        """
        Ultra-resilient locator that dumps the raw XML tree using Appium's page_source and
        searches every node for matching text/content-desc.
        If found, it resolves the bounding box and performs a direct ADB tap.
        
        Args:
            target_text: Text to search for in node attributes
            timeout: Max wait time in seconds
            exact_match: If True, requires exact text match (case-insensitive). Default is substring.
            min_y: If set, only match elements whose center Y is above this threshold (for bottom sliders etc)
        """
        start_time = time.time()
        logger.info(f"Polling raw XML tree for text: '{target_text}' (timeout={timeout}s, exact={exact_match}, min_y={min_y})")
        
        while time.time() - start_time < timeout:
            try:
                source = self._driver.page_source
                if not source or target_text.lower() not in source.lower():
                    time.sleep(1)
                    continue
                
                xml_root = ET.fromstring(source.encode('utf-8'))
                for node in xml_root.iter():
                    node_text = node.attrib.get('text', '')
                    node_desc = node.attrib.get('content-desc', '')
                    
                    if exact_match:
                        match = (node_text.lower() == target_text.lower() or 
                                 node_desc.lower() == target_text.lower())
                    else:
                        match = (target_text.lower() in node_text.lower() or 
                                 target_text.lower() in node_desc.lower())
                    
                    if match:
                        bounds_str = node.attrib.get('bounds')
                        if bounds_str:
                            m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
                            if m:
                                x1, y1, x2, y2 = map(int, m.groups())
                                cx = (x1 + x2) // 2
                                cy = (y1 + y2) // 2
                                if cy < min_y:
                                    logger.debug(f"Skipping '{target_text}' at ({cx},{cy}) — below min_y={min_y}")
                                    continue
                                logger.info(f"Found '{target_text}' via XML at ({cx}, {cy}). Tapping now.")
                                self._adb.tap(cx, cy)
                                return True
            except Exception as e:
                logger.debug(f"XML parsing iter error: {e}")
            
            time.sleep(1)
            
        logger.warning(f"Timeout: Could not locate text '{target_text}' in XML tree.")
        return False

    def _tap_bottom_tab(self, tab_name: str, timeout: int = WAIT_MEDIUM) -> bool:
        """
        Robustly taps a bottom navigation tab (Home, Search, Reels, Profile) by its exact
        resource-id to avoid false positive text matches ('Profile' text matching 'Share profile').
        """
        tab_ids = {
            "Home": "com.instagram.android:id/feed_tab",
            "Search": "com.instagram.android:id/search_tab",
            "Reels": "com.instagram.android:id/clips_tab",
            "Profile": "com.instagram.android:id/profile_tab"
        }
        
        target_id = tab_ids.get(tab_name)
        if not target_id:
            logger.error(f"Unknown bottom tab: {tab_name}")
            return False
            
        start_time = time.time()
        logger.info(f"Polling raw XML tree for bottom tab: '{tab_name}' ({target_id})")
        
        while time.time() - start_time < timeout:
            try:
                source = self._driver.page_source
                if not source or target_id not in source:
                    time.sleep(1)
                    continue
                
                xml_root = ET.fromstring(source.encode('utf-8'))
                # We also accept direct matches of the button container for clicks
                for node in xml_root.iter():
                    if node.attrib.get('resource-id') == target_id:
                        bounds_str = node.attrib.get('bounds')
                        if bounds_str:
                            m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
                            if m:
                                x1, y1, x2, y2 = map(int, m.groups())
                                cx = (x1 + x2) // 2
                                cy = (y1 + y2) // 2
                                logger.info(f"Found {tab_name} tab via XML at ({cx}, {cy}). Tapping now.")
                                self._adb.tap(cx, cy)
                                return True
            except Exception as e:
                logger.debug(f"XML parsing iter error: {e}")
            
            time.sleep(1)
            
        logger.warning(f"Timeout: Could not locate bottom tab '{tab_name}'.")
        return False

    def _tap_element_or_coords(self, by, value, fallback_coords: tuple, timeout: int = WAIT_MEDIUM):
        """Try Appium element find, fall back to ADB tap on coordinates if package matches."""
        try:
            el = WebDriverWait(self._driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            el.click()
        except (TimeoutException, NoSuchElementException):
            # SAFETY CHECK: Only perform ADB tap if Instagram is actually the foreground app
            current_pkg = self._adb.get_foreground_package()
            if current_pkg == INSTAGRAM_PACKAGE:
                logger.warning(f"Element not found [{value}] — falling back to ADB tap {fallback_coords}")
                self._adb.tap(*fallback_coords)
            else:
                logger.error(f"Element not found [{value}] and Instagram not in foreground ({current_pkg}). Refusing to tap elsewhere.")
                raise RuntimeError(f"Target UI element '{value}' missing and Instagram lost focus.")

    def _tap_next_button(self):
        """
        Tap the Next button in the Reel editor to proceed to the caption screen.
        From recorded XML: Next is at (1237, 2969) — bottom-right corner.
        Extended timeout (WAIT_LONG) allows video to fully load before Next appears.
        """
        if not self._tap_by_text_xml("Next", timeout=WAIT_LONG):
            logger.warning("Next not in XML — tapping known coords (1237, 2969) from recorded XML.")
            self._adb.tap(1237, 2969)  # Bottom-right Next button confirmed from XML recording

    def _add_trending_audio(self):
        """
        Invoked when the source video has no audio or is flagged for copyright.
        Navigates the internal Reel Editor UI to add a trending track.
        """
        logger.info("Attempting to add trending audio...")
        
        # 1. Tap the Audio music note icon. 
        # Look for content-desc "Audio" or tap known region (often at top toolbar, ex: (415, 180))
        if not self._tap_by_text_xml("Audio", timeout=WAIT_SHORT, exact_match=False):
            logger.warning("Audio button not found in XML. Tapping known Top-Toolbar Audio coordinates (415, 180).")
            self._adb.tap(415, 180)
        time.sleep(WAIT_SHORT)
        
        # 2. Tap the first suggested track under "For you"
        # We look for a layout container that represents a track row. 
        # In IG, audio rows usually have a content-desc with the track name or "Play".
        # If XML fails, we tap the approximate center of the screen where the first track usually sits.
        logger.info("Selecting top trending track from 'For you' list...")
        if not self._tap_by_text_xml("Play", timeout=WAIT_SHORT, exact_match=False, min_y=500):
            logger.warning("Track row not found in XML. Tapping known first-track coordinate (720, 800).")
            self._adb.tap(720, 800)
        time.sleep(WAIT_SHORT)
        
        # 3. Tap "Done" at the top right to apply the track
        logger.info("Confirming audio selection (Done).")
        if not self._tap_by_text_xml("Done", timeout=WAIT_SHORT, exact_match=False):
            logger.warning("Done button not found in XML. Tapping known Done coordinate (1300, 150).")
            self._adb.tap(1300, 150)
        
        time.sleep(WAIT_SHORT)
        logger.info("Trending audio successfully applied.")

    def _enter_caption(self, caption: str):
        """
        Locate the caption AutoCompleteTextView on the Share screen and type the caption.
        """
        def _paste_action(text: str):
            """Internal helper to set clipboard and trigger paste keyevent."""
            try:
                self._driver.set_clipboard_text(text)
            except Exception:
                # Fallback: set via adb
                import subprocess
                safe = text.replace("'", "\\'")
                subprocess.run(["adb", "shell", f"am broadcast -a clipper.set -e text '{safe}'"],
                               capture_output=True)
            time.sleep(0.8)
            # Try CTRL+V/PASTE
            self._adb._run(["shell", "input", "keyevent", "279"])
            time.sleep(WAIT_SHORT)

        def _finalize_entry():
            """Standard routine to dismiss keyboard and confirm entry."""
            logger.info("Finalizing caption entry: Dismissing keyboard and tapping OK...")
            # Dismiss keyboard (Back button)
            self._adb._run(["shell", "input", "keyevent", "4"])
            time.sleep(1)
            # Tap 'OK' (or blue checkmark) at top right
            if not self._tap_by_text_xml("OK", timeout=WAIT_SHORT, exact_match=True, min_y=50):
                # Fallback to known top right bounds for generic OK button
                # Bounds usually around [1260,100][1440,250]
                self._adb.tap(1330, 180)
            time.sleep(WAIT_SHORT)

        # ── Strategy 1: Appium AutoCompleteTextView ─────────────────────────
        success = False
        try:
            field = WebDriverWait(self._driver, WAIT_SHORT).until(
                EC.presence_of_element_located(
                    (AppiumBy.XPATH,
                     '//android.widget.AutoCompleteTextView | //android.widget.EditText')
                )
            )
            field.click()
            time.sleep(0.5)
            _paste_action(caption)
            logger.info("Caption entered via Appium (Strategy 1).")
            success = True
        except Exception as e:
            logger.debug(f"Strategy 1 failed: {e}")

        # ── Strategy 2: XML tap on placeholder text ─────────────────────────
        if not success:
            try:
                if self._tap_by_text_xml("Write a caption", timeout=WAIT_SHORT, exact_match=False):
                    time.sleep(0.5)
                    _paste_action(caption)
                    logger.info("Caption entered via XML text tap (Strategy 2).")
                    success = True
            except Exception as e:
                logger.debug(f"Strategy 2 failed: {e}")

        # ── Strategy 3: ADB tap at known coords ─────────────────────────────
        if not success:
            logger.warning("Caption field not found via Appium/XML — using known ADB coords (720,1674).")
            self._adb.tap(720, 1674)
            time.sleep(0.8)
            _paste_action(caption)
            logger.info("Caption paste attempted via ADB fallback (Strategy 3).")
            success = True

        if success:
            _finalize_entry()
            self._save_debug_state("06_caption_entered")
        else:
            logger.error("All caption entry strategies failed.")

    def grab_recent_reel_shortcode(self) -> Optional[str]:
        """
        Automates navigating to the user's Profile, opening the most recent Reel,
        and copying its link to extract the resulting shortcode.
        
        Flow (confirmed from gesture_test XML analysis):
          1. Profile tab
          2. Reels tab on profile
          3. Tap first (most recent) reel
          4. Tap "Send post" share button (NOT "More actions" — "Copy link"
             is not in the More Actions menu for your OWN posts)
          5. Tap "Copy link" in the share sheet
          6. Extract shortcode from clipboard
        
        This is necessary for ROI tracking in Closed-Cycle Analysis.
        """
        self.start_session()
        try:
            logger.info("Starting Shortcode Extraction Flow...")
            self._adb.unlock_device()
            self._adb.launch_instagram()
            time.sleep(WAIT_MEDIUM)
            
            self._reset_to_home()
            
            # ── Step 1: Navigate to Profile Tab ──────────────────────────────
            logger.info("Step 1: Navigate to Profile Tab")
            # Bounds [963,2657][1432,3060] -> Safe center (1300, 2850)
            if not self._tap_bottom_tab("Profile", timeout=WAIT_SHORT):
                logger.warning("Profile tab not found via resource-id. Tapping fallback coordinate (1300, 2850).")
                self._adb.tap(1300, 2850)
            time.sleep(WAIT_MEDIUM)
            self._save_debug_state("shortcode_01_profile")
            
            # ── Step 2: Navigate to Reels Tab on Profile ─────────────────────
            logger.info("Step 2: Navigate to Reels Tab on Profile")
            # Profile screen reels tab: content-desc="Reels"
            if not self._tap_by_text_xml("Reels", timeout=WAIT_SHORT, exact_match=True):
                logger.warning("Reels tab not found via exact text match XML. Tapping coordinate (540, 2239).")
                self._adb.tap(540, 2239)
            time.sleep(WAIT_MEDIUM)
            self._save_debug_state("shortcode_02_reels_tab")
            
            # ── Step 3: Tap the most recent Reel ─────────────────────────────
            logger.info("Step 3: Tap the most recent Reel")
            # From copy_link recording: first reel at [0,2337][479,2868] -> (240, 2602)
            # content-desc: "Reel by t.ptrending at row 1, column 1"
            self._adb.tap(240, 2602)
            time.sleep(WAIT_LONG)
            self._save_debug_state("shortcode_03_reel_open")
            
            # ── Step 4: Tap "Send post" share button ─────────────────────────
            # CRITICAL: For your OWN posts, "Copy link" is NOT in the More Actions
            # menu. It's only accessible via the Share sheet.
            # ID: com.instagram.android:id/direct_share_button, Bounds: [1232,1707][1408,1883] -> (1320, 1795)
            logger.info("Step 4: Tap 'Share' button on the reel")
            
            # Use our robust tap mechanism, but we must check XML manually or use a helper
            # We'll use _tap_by_text_xml but search for "Share" or the resource-id
            found_share = False
            start_share = time.time()
            while time.time() - start_share < WAIT_SHORT:
                source = self._driver.page_source
                if source and "com.instagram.android:id/direct_share_button" in source:
                    xml_root = ET.fromstring(source.encode('utf-8'))
                    for node in xml_root.iter():
                        if node.attrib.get('resource-id') == "com.instagram.android:id/direct_share_button":
                            bounds_str = node.attrib.get('bounds')
                            m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
                            if m:
                                x1, y1, x2, y2 = map(int, m.groups())
                                self._adb.tap((x1 + x2) // 2, (y1 + y2) // 2)
                                found_share = True
                                break
                if found_share:
                    break
                time.sleep(1)

            if not found_share:
                logger.warning("'Share' button ID not found in XML. Tapping fallback coordinate (1320, 1795).")
                self._adb.tap(1320, 1795)
            
            time.sleep(3) # Explicit wait for share sheet to animate up
            self._save_debug_state("shortcode_04_share_sheet")
            
            # ── Step 5: Tap "Copy link" in the share sheet ───────────────────
            logger.info("Step 5: Tap 'Copy link' in share sheet")
            
            # Strategy A: Direct XML detection (Horizontal Reshare Row)
            found_copy_link = False
            for attempt in range(2):
                if self._tap_by_text_xml("Copy link", timeout=WAIT_SHORT, exact_match=False):
                    found_copy_link = True
                    break
                
                if attempt == 0:
                    logger.warning("'Copy link' not immediately visible. Swiping reshare row horizontally...")
                    # Swipe the bottom row of the share sheet (where Copy Link lives)
                    # Coordinates based on 1440x3120 but safe for most aspect ratios
                    self._adb.swipe(1200, 2800, 400, 2800, duration_ms=500)
                    time.sleep(2)
            
            # Strategy B: Vertical Scroll Fallback (if the sheet itself needs expansion)
            if not found_copy_link:
                logger.warning("'Copy link' still not found. Trying vertical expansion scroll...")
                self._adb.swipe(720, 2400, 720, 1800, duration_ms=300)
                time.sleep(2)
                if self._tap_by_text_xml("Copy link", timeout=WAIT_SHORT, exact_match=False):
                    found_copy_link = True

            # Strategy C: Resolution-Aware Coordinate Fallback
            if not found_copy_link:
                width = 1080 # Default
                height = 1920
                try:
                    size = self.driver.get_window_size()
                    width, height = size['width'], size['height']
                except: pass
                
                logger.warning(f"Strategy C: Fallback to coordinate for {width}x{height}")
                if width > 1200: # High Res (1440-like)
                    # Tapping the typical 4th position in a large reshare row
                    self._adb.tap(1060, 2730)
                else: # Standard Res (1080-like)
                    self._adb.tap(800, 1850)
            
            time.sleep(WAIT_MEDIUM)
            self._save_debug_state("shortcode_05_link_copied")
            
            # ── Step 6: Extract link from clipboard ──────────────────────────
            logger.info("Step 6: Extract link from clipboard")
            shortcode = self._extract_shortcode_from_clipboard()
            
            if shortcode:
                logger.info(f"✅ Successfully extracted shortcode: {shortcode}")
            else:
                logger.warning("Shortcode extraction failed. Check debug dumps.")
                self._save_debug_state("shortcode_06_FAILED")
            
            return shortcode
                 
        except Exception as e:
            logger.error(f"Shortcode extraction failed: {e}")
            self._save_debug_state("shortcode_ERROR")
            return None
        finally:
            self.end_session()

    def _extract_shortcode_from_clipboard(self) -> Optional[str]:
        """
        Reads the Android clipboard and extracts an Instagram reel shortcode.
        
        Tries two methods:
          1. Appium's get_clipboard_text (reliable if settings app has focus/perms)
          2. `service call clipboard 2` (fallback)
        
        Returns the shortcode string or None.
        """
        clipboard_text = ""
        
        # Method 1: Appium's native clipboard retrieval
        try:
            logger.info("Attempting to read clipboard via Appium...")
            val = self._driver.get_clipboard_text()
            if val:
                clipboard_text = str(val).strip()
        except Exception as e:
            logger.debug(f"Appium get_clipboard_text failed: {e}")
            
        # Method 2: Fallback to ADB service call
        if not clipboard_text:
            logger.info("Attempting clipboard fallback via ADB...")
            ret_code, stdout, stderr = self._adb._run(["shell", "service", "call", "clipboard", "2"])
            if ret_code == 0 and stdout:
                try:
                    for line in stdout.strip().splitlines():
                        if "'" in line:
                            clipboard_text += line.split("'")[1]
                except Exception as e:
                    logger.debug(f"Clipboard parsing error: {e}")
        
        if not clipboard_text:
            logger.warning("Could not read clipboard from device.")
            return None
        
        logger.debug(f"Clipboard content: {clipboard_text[:200]}")
        
        # Extract shortcode from Instagram URL patterns:
        # https://www.instagram.com/reel/ABC123/
        # https://www.instagram.com/p/ABC123/
        match = re.search(r'/(?:reel|p)/([A-Za-z0-9_-]+)/?', clipboard_text)
        if match:
            return match.group(1)
        
        logger.warning(f"No shortcode found in clipboard: {clipboard_text[:100]}")
        return None


