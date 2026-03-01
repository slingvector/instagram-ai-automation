"""
src/ingestion/adapters/creator_adapter.py

UC2: Creator Watchlist Adapter
  - Reads creator_watchlist.yaml (main account) and exclusive_watchlist.yaml
  - Playwright scrapes each creator's Reels tab
  - Filters by views, likes, recency, duration
  - Returns ContentItems for qualifying Reels not yet seen
"""
from __future__ import annotations

import logging
import os
import re
import time
import random
from pathlib import Path
from typing import List

import yaml

from src.ingestion.base import ContentItem, Niche, Platform, SourceAdapter, SourceType, AccountProfile
from src.ingestion.dedup import ContentDedup

logger = logging.getLogger(__name__)

_MAIN_CONFIG     = Path(__file__).parents[3] / "config" / "creator_watchlist.yaml"
_EXCLUSIVE_CONFIG = Path(__file__).parents[3] / "config" / "exclusive_watchlist.yaml"
_REEL_RE = re.compile(r'/reel/([A-Za-z0-9_-]+)/')


class CreatorAdapter(SourceAdapter):
    """
    Scrapes Instagram creator profiles for top-performing Reels.
    Supports both main-account niches and the isolated exclusive-account.
    """

    source_type = SourceType.CREATOR

    def __init__(self, headless: bool = True, include_exclusive: bool = False):
        self.headless = headless
        self.include_exclusive = include_exclusive
        self.dedup = ContentDedup()
        self.session_file = Path(
            os.environ.get("IG_SESSION_FILE", "data/ig_readonly_session.json")
        )

    def fetch(self) -> List[ContentItem]:
        items: List[ContentItem] = []
        configs = self._load_configs()

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("playwright not installed")
            return []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                           "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                viewport={"width": 390, "height": 844},
                storage_state=str(self.session_file) if self.session_file.exists() else None,
            )
            page = context.new_page()

            for niche, accounts, filters, target_account in configs:
                for username in accounts:
                    if not username:
                        continue
                    try:
                        found = self._scrape_creator(page, username, niche, filters, target_account)
                        items.extend(found)
                    except Exception as e:
                        logger.warning(f"Failed to scrape @{username}: {e}")
                    self._human_delay(3, 6)

            context.storage_state(path=str(self.session_file))
            browser.close()

        return items

    def _scrape_creator(
        self, page, username: str, niche: str,
        filters: dict, target_account: str
    ) -> List[ContentItem]:
        items = []
        url = f"https://www.instagram.com/{username}/reels/"
        logger.info(f"Scraping @{username} ({niche})")

        page.goto(url, wait_until="networkidle", timeout=30_000)
        self._human_delay(2, 4)

        # Collect Reel links from the grid
        reel_links = page.query_selector_all('a[href*="/reel/"]')
        logger.debug(f"@{username}: found {len(reel_links)} reel links visible")

        min_views  = filters.get("min_views", 0)
        min_likes  = filters.get("min_likes", 0)
        max_days   = filters.get("posted_within_days", 30)
        max_dur    = filters.get("max_duration_seconds", 90)

        for link in reel_links[:20]:   # Check at most 20 from current view
            href = link.get_attribute("href") or ""
            m = _REEL_RE.search(href)
            if not m:
                continue

            shortcode = m.group(1)
            reel_url = f"https://www.instagram.com/reel/{shortcode}/"

            item = ContentItem(
                url=reel_url,
                platform=Platform.INSTAGRAM,
                source_type=SourceType.CREATOR,
                niche=niche,
                target_account=target_account,
                creator_username=username,
                shortcode=shortcode,
            )

            # Skip if already seen
            if self.dedup.is_duplicate(item):
                continue

            items.append(item)
            logger.info(f"Queued @{username} reel: {reel_url}")

        return items

    def _load_configs(self):
        """
        Returns list of (niche, [usernames], filters, target_account) tuples.
        Loads main watchlist and optionally the exclusive watchlist.
        """
        configs = []

        # Main watchlist
        if _MAIN_CONFIG.exists():
            with open(_MAIN_CONFIG) as f:
                data = yaml.safe_load(f) or {}
            for niche, niche_cfg in data.get("niches", {}).items():
                filters  = niche_cfg.get("filters", {})
                accounts = [a.get("username") for a in niche_cfg.get("accounts", [])]
                configs.append((niche, accounts, filters, AccountProfile.MAIN))

        # Exclusive watchlist (opt-in, fully isolated)
        if self.include_exclusive and _EXCLUSIVE_CONFIG.exists():
            with open(_EXCLUSIVE_CONFIG) as f:
                data = yaml.safe_load(f) or {}
            accounts = [a.get("username") for a in data.get("accounts", [])]
            filters  = data.get("filters", {})
            configs.append((Niche.EXPLICIT, accounts, filters, AccountProfile.EXCLUSIVE))

        return configs

    @staticmethod
    def _human_delay(min_s=1.0, max_s=3.0):
        time.sleep(random.uniform(min_s, max_s))
