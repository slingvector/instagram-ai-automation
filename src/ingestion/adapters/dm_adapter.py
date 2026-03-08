"""
src/ingestion/adapters/dm_adapter.py

UC1: Instagram DM Scraper
  - Logs into the READ-ONLY Instagram account via Playwright (stealth mode)
  - Iterates unread DM threads
  - Extracts Instagram Reel URLs from messages
  - Tracks seen message IDs in SQLite (inbox is NEVER marked as read)
  - Returns List[ContentItem] for downstream processing
"""
from __future__ import annotations

import logging
import os
import re
import time
import random
from pathlib import Path
from typing import List, Optional

from src.ingestion.base import ContentItem, Niche, Platform, SourceAdapter, SourceType, AccountProfile
from src.ingestion.dedup import ContentDedup

logger = logging.getLogger(__name__)

# Regex to extract IG reel shortcodes from any IG URL format
_REEL_URL_RE = re.compile(
    r'https?://(?:www\.)?instagram\.com/(?:reel|p|reels)/([A-Za-z0-9_-]+)/?'
)

# Default niche for DM-sourced content — can be overridden per sender
_DEFAULT_NICHE = Niche.ENTERTAINMENT


class DMAdapter(SourceAdapter):
    """
    Playwright-based adapter that reads Instagram DMs from a read-only account
    and extracts Reel URLs. Never marks messages as read on the actual platform —
    dedup is handled via local SQLite only.

    Environment variables required:
      IG_READONLY_USERNAME  — read-only IG account username
      IG_READONLY_PASSWORD  — read-only IG account password
      IG_SESSION_FILE       — path to saved Playwright session cookies (optional)
    """

    source_type = SourceType.DM

    def __init__(self, headless: bool = True, max_threads: int = 20, thread_whitelist: List[str] = None):
        self.headless = headless
        self.max_threads = max_threads       # Max DM threads to check per run
        
        # Load thread whitelist from env if not provided
        if thread_whitelist is None:
            env_whitelist = os.environ.get("IG_THREAD_WHITELIST", "")
            self.thread_whitelist = [tid.strip() for tid in env_whitelist.split(",") if tid.strip()]
        else:
            self.thread_whitelist = thread_whitelist
            
        self.dedup = ContentDedup()
        self.username = os.environ.get("IG_READONLY_USERNAME", "")
        self.password = os.environ.get("IG_READONLY_PASSWORD", "")
        self.session_file = Path(
            os.environ.get("IG_SESSION_FILE", "data/ig_readonly_session.json")
        )

    def fetch(self) -> List[ContentItem]:
        """
        Open Instagram DMs via Playwright, extract Reel URLs from unread threads.
        Returns ContentItems for new, unseen messages only.
        """
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
        except ImportError:
            logger.error("playwright not installed. Run: pip install playwright && playwright install chromium")
            return []

        items: List[ContentItem] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = self._make_context(browser, p)
            page = context.new_page()

            # Attach browser debug listeners
            page.on("console", lambda msg: logger.debug(f"BROWSER CONSOLE [{msg.type}]: {msg.text}"))
            page.on("requestfailed", lambda req: logger.debug(f"BROWSER HTTP FAIL: {req.url} — {req.failure}"))
            
            self._api_shortcodes = set()
            
            def handle_response(response):
                try:
                    if "api/v1/direct_v2" in response.url or "graphql" in response.url:
                        if response.request.resource_type in ["fetch", "xhr"]:
                            text = response.text()
                            # Shortcodes are exactly 11 characters typically, but we allow 11-15 
                            matches = re.findall(r'"(?:code|shortcode|clip_url|video_url)":"([^"]+)"', text)
                            for m in matches:
                                if re.match(r'^[A-Za-z0-9_-]{11,15}$', m):
                                    self._api_shortcodes.add(m)
                                elif "/reel/" in m or "/reels/" in m:
                                    url_m = re.search(r'/(?:reel|reels)/([A-Za-z0-9_-]+)', m)
                                    if url_m:
                                        self._api_shortcodes.add(url_m.group(1))
                            
                            # Fallback for hidden URLs in the JSON payload
                            fallback_urls = re.findall(r'/(?:reel|reels)/([A-Za-z0-9_-]+)[/"\'\\]', text)
                            for u in fallback_urls:
                                self._api_shortcodes.add(u)
                except Exception:
                    pass

            page.on("response", handle_response)

            try:
                self._login(page)
                items = self._scrape_dms(page)
            except KeyboardInterrupt:
                logger.info("Scraping manually stopped by user.")
            except Exception as e:
                logger.error(f"DM scraping failed: {e}")
            finally:
                # Save updated session cookies
                try:
                    context.storage_state(path=str(self.session_file))
                except Exception as e:
                    logger.debug(f"Could not save storage state (maybe browser closed): {e}")
                browser.close()

        return items

    # ── Session & login ───────────────────────────────────────────────────────

    def _make_context(self, browser, p):
        """Create a stealth browser context, loading saved session if available."""
        context_kwargs = {
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1280, "height": 800},
            "locale": "en-US",
            "device_scale_factor": 2,
        }
        
        use_proxy = os.environ.get("USE_PROXY_FOR_INGESTION", "false").lower() == "true"
        proxy_url = os.environ.get("PROXY_SERVER")
        
        if use_proxy and proxy_url:
            context_kwargs["proxy"] = {"server": proxy_url}
            
        if self.session_file.exists():
            context_kwargs["storage_state"] = str(self.session_file)

        return browser.new_context(**context_kwargs)

    def _login(self, page) -> None:
        """Login to Instagram if not already authenticated via saved session."""
        logger.info("Checking login state...")
        page.goto("https://www.instagram.com/")
        self._human_delay(3, 5)

        # Check if already logged in (look for home icon)
        try:
            page.wait_for_selector('svg[aria-label="Home"], a[href="/"]', timeout=5000)
            logger.info("Already logged in via saved session.")
            return
        except Exception:
            pass

        logger.info("Logging in to read-only IG account...")
        page.goto("https://www.instagram.com/accounts/login/")
        self._human_delay(3, 5)

        try:
            page.fill('input[name="username"]', self.username)
            self._human_delay(1, 2)
            page.fill('input[name="password"]', self.password)
            self._human_delay(1, 2)
            page.click('button[type="submit"]')
        except Exception as e:
            logger.warning(f"Could not auto-fill login: {e}")

        logger.info("Waiting for successful login (up to 60s for captcha/2FA)...")
        try:
            page.wait_for_selector('svg[aria-label="Home"], a[href="/"]', timeout=60_000)
            self._human_delay(2, 4)
            logger.info("Login successful.")
        except PlaywrightTimeoutError:
            logger.error("Login timed out. Handle CAPTCHA or 2FA manually faster.")
            raise

    # ── DM scraping ───────────────────────────────────────────────────────────

    def _scrape_dms(self, page) -> List[ContentItem]:
        """Navigate to DM inbox and extract Reel URLs from message threads."""
        items: List[ContentItem] = []

        logger.info("Loading Home feed to simulate human flow...")
        page.goto("https://www.instagram.com/")
        self._human_delay(3, 5)

        logger.info("Simulating human scroll on Home feed...")
        page.mouse.wheel(0, 800)
        self._human_delay(1, 2)
        page.mouse.wheel(0, -400)
        self._human_delay(2, 3)

        logger.info("Clicking Messages icon in sidebar...")
        try:
            page.click('a[href^="/direct/inbox/"]', timeout=5000)
            self._human_delay(3, 5)
        except Exception as e:
            logger.warning(f"Failed to click Messages link: {e}. Falling back to URL.")
            page.goto("https://www.instagram.com/direct/inbox/")
            self._human_delay(3, 5)

        # Wait for the Thread list container (Desktop UI)
        try:
            logger.info("Waiting for DM threads to render (up to 15s)...")
            page.wait_for_selector('[aria-label="Thread list"]', timeout=15_000)
        except PlaywrightTimeoutError:
            logger.debug("No DM Thread list found within timeout.")

        threads = []
        thread_container = page.query_selector('[aria-label="Thread list"]')
        if thread_container:
            # Get all role="button" inside. The first few are usually headers/notes.
            buttons = thread_container.query_selector_all('div[role="button"]')
            for b in buttons:
                text = b.inner_text().strip()
                # Skip the user's own header and compose/note buttons
                if not text or text == "New message" or "your note" in text.lower():
                    continue
                # Skip the header with the username
                if text.startswith(self.username):
                    continue
                # Skip tablist buttons if any slipped through
                if text in ["Primary", "General", "Requests"]:
                    continue
                threads.append(b)

        logger.info(f"Found {len(threads)} DM threads. Checking up to {self.max_threads}.")

        for thread in threads[:self.max_threads]:
            try:
                # Safely get the thread name for logging
                t_name = thread.inner_text().split('\n')[0]
                
                # If whitelist is enabled, we need to click to check the ID
                # or find a way to check it beforehand. For now, we click and skip.
                thread.click()
                self._human_delay(3, 5)
                
                current_thread_id = page.url.strip('/').split('/')[-1]
                if self.thread_whitelist and current_thread_id not in self.thread_whitelist:
                    logger.info(f"Skipping non-whitelisted thread: {t_name} ({current_thread_id})")
                    continue

                logger.info(f"Processing whitelisted thread: {t_name} ({current_thread_id})")
                thread_items = self._process_thread_content(page, current_thread_id)
                items.extend(thread_items)
            except Exception as e:
                logger.error(f"Thread processing error: {e}", exc_info=True)
            self._human_delay(2, 4)

        return items

    def _process_thread_content(self, page, thread_id: str) -> List[ContentItem]:
        """Extract new Reel URLs from the currently active DM thread."""
        items: List[ContentItem] = []

        try:
            page.wait_for_selector('a[href]', timeout=10_000)
        except PlaywrightTimeoutError:
            pass
            
        try:
            html = page.content()
            dump_path = Path(f"debug/thread_{thread_id}.html")
            dump_path.write_text(html, encoding="utf-8")
        except Exception as e:
            logger.debug(f"Failed to dump thread HTML: {e}")

        # Pagination to load older messages if not all are in initial payload
        logger.info(f"Scrolling up to load older messages for thread {thread_id} (Pagination)...")
        # Hover near the center where the messages usually are
        try:
            page.mouse.move(640, 400) # center of 1280x800 viewport
            for _ in range(3):
                page.mouse.wheel(0, -3000) # Scroll up
                self._human_delay(1.5, 2.5)
        except Exception as wheel_err:
            logger.debug(f"Could not scroll up to paginate: {wheel_err}")

        # Give the API responses time to fully arrive
        self._human_delay(2, 4)

        # 1. Gather all shortcodes intercepted from backend JSON during this thread click
        shortcodes = list(self._api_shortcodes)
        self._api_shortcodes.clear()
        
        # 2. Add any shortcodes found natively in the URL (unlikely but safe)
        if "/reel/" in page.url or "/reels/" in page.url:
            shortcode = page.url.strip('/').split('/')[-1]
            shortcodes.append(shortcode)
            
        logger.info(f"[DEBUG] Extracting intercept shortcodes: {shortcodes}")

        seen_in_this_thread = set()
        for shortcode in shortcodes:
            if shortcode.lower() == "audio" or len(shortcode) < 8 or shortcode in seen_in_this_thread:
                continue
                
            seen_in_this_thread.add(shortcode)

            # Derive a stable message_id from thread URL + shortcode
            thread_url = page.url
            message_id = f"{thread_url.split('/')[-1]}::{shortcode}"

            # Skip if we've already processed this DM
            if self.dedup.is_dm_seen(message_id):
                logger.info(f"DM already seen: {message_id}")
                continue

            # Use the /reel/ URL structure instead of /p/ to ensure yt-dlp
            # correctly parses Instagram Reels using its dedicated unauthenticated extractor.
            url = f"https://www.instagram.com/reel/{shortcode}/"
            item = ContentItem(
                url=url,
                platform=Platform.INSTAGRAM,
                source_type=SourceType.DM,
                niche=_DEFAULT_NICHE,
                target_account=AccountProfile.MAIN,
                shortcode=shortcode,
                raw_metadata={"message_id": message_id, "thread_url": thread_url},
            )
            items.append(item)

            # Removed: self.dedup.register_dm(...)
            # Dedup state is now managed downstream upon successful post!
            logger.info(f"New DM reel queued (unregistered): {url}")

        return items

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _human_delay(min_s: float = 0.5, max_s: float = 2.0) -> None:
        """Random delay to mimic human browsing behavior."""
        time.sleep(random.uniform(min_s, max_s))
