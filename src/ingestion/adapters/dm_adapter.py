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

    def __init__(self, headless: bool = True, max_threads: int = 20):
        self.headless = headless
        self.max_threads = max_threads       # Max DM threads to check per run
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
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("playwright not installed. Run: pip install playwright && playwright install chromium")
            return []

        items: List[ContentItem] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = self._make_context(browser, p)
            page = context.new_page()

            try:
                self._login(page)
                items = self._scrape_dms(page)
            except Exception as e:
                logger.error(f"DM scraping failed: {e}")
            finally:
                # Save updated session cookies
                context.storage_state(path=str(self.session_file))
                browser.close()

        return items

    # ── Session & login ───────────────────────────────────────────────────────

    def _make_context(self, browser, p):
        """Create a stealth browser context, loading saved session if available."""
        context_kwargs = {
            "user_agent": (
                "Mozilla/5.0 (Linux; Android 11; Pixel 5) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Mobile Safari/537.36"
            ),
            "viewport": {"width": 390, "height": 844},
            "locale": "en-US",
        }
        if self.session_file.exists():
            context_kwargs["storage_state"] = str(self.session_file)

        return browser.new_context(**context_kwargs)

    def _login(self, page) -> None:
        """Login to Instagram if not already authenticated via saved session."""
        page.goto("https://www.instagram.com/", wait_until="networkidle", timeout=30_000)
        self._human_delay(2, 4)

        # Check if already logged in
        if page.url.startswith("https://www.instagram.com/") and \
           page.query_selector('[aria-label="Instagram"]') is not None:
            try:
                # Look for login form; if absent, we're already in
                page.wait_for_selector('input[name="username"]', timeout=3_000)
            except Exception:
                logger.info("Already logged in via saved session.")
                return

        logger.info("Logging in to read-only IG account...")
        page.goto("https://www.instagram.com/accounts/login/", wait_until="networkidle", timeout=30_000)
        self._human_delay(1, 3)

        page.fill('input[name="username"]', self.username)
        self._human_delay(0.5, 1.5)
        page.fill('input[name="password"]', self.password)
        self._human_delay(0.5, 1.5)
        page.click('button[type="submit"]')

        # Wait for redirect away from login page
        page.wait_for_url("https://www.instagram.com/**", timeout=15_000)
        self._human_delay(2, 4)
        logger.info("Login successful.")

    # ── DM scraping ───────────────────────────────────────────────────────────

    def _scrape_dms(self, page) -> List[ContentItem]:
        """Navigate to DM inbox and extract Reel URLs from message threads."""
        items: List[ContentItem] = []

        logger.info("Navigating to DM inbox...")
        page.goto("https://www.instagram.com/direct/inbox/", wait_until="networkidle", timeout=30_000)
        self._human_delay(2, 3)

        # Find DM thread list items
        threads = page.query_selector_all('[role="listitem"]')
        logger.info(f"Found {len(threads)} DM threads. Checking up to {self.max_threads}.")

        for thread in threads[:self.max_threads]:
            try:
                thread_items = self._process_thread(page, thread)
                items.extend(thread_items)
            except Exception as e:
                logger.debug(f"Thread processing error: {e}")
            self._human_delay(1, 2)

        return items

    def _process_thread(self, page, thread) -> List[ContentItem]:
        """Click a thread and extract new Reel URLs from its messages."""
        items: List[ContentItem] = []

        thread.click()
        self._human_delay(1.5, 3)

        # Grab all message links in the visible thread
        links = page.query_selector_all('a[href*="instagram.com/reel"], a[href*="instagram.com/p/"]')

        for link in links:
            href = link.get_attribute("href") or ""
            m = _REEL_URL_RE.search(href)
            if not m:
                continue

            shortcode = m.group(1)
            # Derive a stable message_id from thread URL + shortcode
            thread_url = page.url
            message_id = f"{thread_url.split('/')[-1]}::{shortcode}"

            # Skip if we've already processed this DM
            if self.dedup.is_dm_seen(message_id):
                logger.debug(f"DM already seen: {message_id}")
                continue

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

            # Register in SQLite so we never process this DM again
            self.dedup.register_dm(message_id, thread_url, url)
            logger.info(f"New DM reel queued: {url}")

        return items

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _human_delay(min_s: float = 0.5, max_s: float = 2.0) -> None:
        """Random delay to mimic human browsing behavior."""
        time.sleep(random.uniform(min_s, max_s))
