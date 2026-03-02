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
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from src.publishing_edge.services.adb_client import ADBClient
from src.publishing_edge.config import (
    APPIUM_HOST, DEVICE_UDID, INSTAGRAM_PACKAGE,
    INSTAGRAM_ACTIVITY, NEW_COMMAND_TIMEOUT
)

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
        """Initialize the Appium driver session. Safe to call multiple times."""
        if self._driver:
            logger.info("Appium session already active.")
            return

        options = self._build_options()
        try:
            logger.info(f"Starting Appium session on {APPIUM_HOST} ...")
            self._driver = webdriver.Remote(APPIUM_HOST, options=options)
            logger.info("Appium session started successfully.")
        except Exception as e:
            logger.error(f"Appium session start failed: {e}. Attempting ADB wake recovery...")
            self._adb.wake_screen()
            time.sleep(2)
            self._driver = webdriver.Remote(APPIUM_HOST, options=options)

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
        options.set_capability("appium:adbHost", "host.docker.internal")
        options.set_capability("appium:adbPort", 5037)
        
        # Note: skipServerInstallation removed so Appium can reinstall UIAutomator2 APKs if needed
        if DEVICE_UDID:
            options.udid = DEVICE_UDID
        return options

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
            logger.info("Step 1: Wake screen and ensure Instagram is in foreground.")
            self._adb.wake_screen()
            self._adb.launch_instagram()
            time.sleep(WAIT_MEDIUM)
            self._save_debug_state("01_instagram_launched")

            logger.info("Step 2: Tap the '+' create button.")
            self._tap_element_or_coords(
                by=AppiumBy.ACCESSIBILITY_ID,
                value="New post",
                fallback_coords=(96, 225),  # top-left corner for new IG layouts
            )
            time.sleep(WAIT_MEDIUM)
            self._save_debug_state("02_after_create_tap")

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

    def _tap_element_or_coords(self, by, value, fallback_coords: tuple, timeout: int = WAIT_MEDIUM):
        """Try Appium element find, fall back to ADB tap on coordinates."""
        try:
            el = WebDriverWait(self._driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            el.click()
        except (TimeoutException, NoSuchElementException):
            logger.warning(f"Element not found [{value}] — falling back to ADB tap {fallback_coords}")
            self._adb.tap(*fallback_coords)

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

        From recorded XML (debug/05_after_next.xml):
          - class: android.widget.AutoCompleteTextView
          - text:  "Write a caption and add hashtags…"
          - bounds: [64,1578][1376,1770]  →  center: (720, 1674)

        Strategy 1: Appium AutoCompleteTextView direct interaction
        Strategy 2: XML-based tap on the placeholder text, then clipboard paste
        Strategy 3: ADB tap at known coords (720,1674), then clipboard paste
        """
        def _paste_via_clipboard(text: str):
            """Set clipboard and paste using Ctrl+V or KEYCODE_PASTE."""
            try:
                self._driver.set_clipboard_text(text)
            except Exception:
                # Fallback: set via adb
                import subprocess
                safe = text.replace("'", "\\'")
                subprocess.run(["adb", "shell", f"am broadcast -a clipper.set -e text '{safe}'"],
                               capture_output=True)
            time.sleep(0.8)
            # Try CTRL+V first (most reliable on Samsung)
            self._adb._run(["shell", "input", "keyevent", "--longpress", "279"])
            time.sleep(0.5)
            # Also try PASTE keycode as backup
            self._adb._run(["shell", "input", "keyevent", "279"])
            time.sleep(WAIT_SHORT)

        # ── Strategy 1: Appium AutoCompleteTextView ─────────────────────────
        try:
            field = WebDriverWait(self._driver, WAIT_SHORT).until(
                EC.presence_of_element_located(
                    (AppiumBy.XPATH,
                     '//android.widget.AutoCompleteTextView | //android.widget.EditText')
                )
            )
            field.click()
            time.sleep(0.5)
            # Use clipboard paste to support emojis
            self._driver.set_clipboard_text(caption)
            time.sleep(0.5)
            self._adb._run(["shell", "input", "keyevent", "279"])  # KEYCODE_PASTE
            time.sleep(WAIT_SHORT)
            logger.info("Caption entered via Appium (Strategy 1).")
            self._save_debug_state("06_caption_entered")
            return
        except Exception as e:
            logger.debug(f"Strategy 1 failed: {e}")

        # ── Strategy 2: XML tap on placeholder text ─────────────────────────
        try:
            if self._tap_by_text_xml("Write a caption", timeout=WAIT_SHORT, exact_match=False):
                time.sleep(0.5)
                _paste_via_clipboard(caption)
                logger.info("Caption entered via XML text tap (Strategy 2).")
                self._save_debug_state("06_caption_entered")
                return
        except Exception as e:
            logger.debug(f"Strategy 2 failed: {e}")

        # ── Strategy 3: ADB tap at known coords from recorded XML ───────────
        logger.warning("Caption field not found via Appium/XML — using known ADB coords (720,1674).")
        self._adb.tap(720, 1674)   # AutoCompleteTextView center from Step 5 XML dump
        time.sleep(0.8)
        _paste_via_clipboard(caption)
        logger.info("Caption paste attempted via ADB fallback (Strategy 3).")
        self._save_debug_state("06_caption_entered")

