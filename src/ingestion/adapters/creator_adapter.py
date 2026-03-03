"""
src/ingestion/adapters/creator_adapter.py

UC2: Top Creator Watchlist
Scrapes specific IG profiles configured in YAML files to discover viral Reels.
Uses Playwright to extract shortcodes, then UniversalDownloader to check metadata (views/likes).
"""
from __future__ import annotations

import logging
import os
import random
import time
import yaml
from pathlib import Path
from typing import List

from src.ingestion.base import ContentItem, Platform, SourceAdapter, SourceType
from src.ingestion.dedup import ContentDedup
from src.ingestion.downloader import UniversalDownloader

logger = logging.getLogger(__name__)

class CreatorAdapter(SourceAdapter):
    source_type = SourceType.CREATOR

    def __init__(self, config_paths: List[str] = None, headless: bool = True):
        if config_paths is None:
            config_paths = ["config/creator_watchlist.yaml", "config/exclusive_watchlist.yaml"]
            
        self.config_paths = [Path(p) for p in config_paths]
        self.headless = headless
        self.dedup = ContentDedup()
        self.downloader = UniversalDownloader(output_dir=Path("data/downloads/tmp"))
        self.session_file = Path(os.environ.get("IG_SESSION_FILE", "data/ig_readonly_session.json"))
        
        self.watchlists = self._load_configs()

    def _load_configs(self) -> dict:
        combined = {
            "filters": {
                "min_views": 500000,
                "min_likes": 10000,
            },
            "creators": {}
        }
        
        for cp in self.config_paths:
            if not cp.exists():
                logger.warning(f"Creator config not found: {cp}")
                continue
                
            with open(cp, "r", encoding="utf-8") as f:
                try:
                    data = yaml.safe_load(f) or {}
                    
                    # Merge filters (first config takes precedence, or we could overwrite. We'll overwrite for simplicity if provided)
                    if "filters" in data:
                        combined["filters"].update(data["filters"])
                        
                    # Merge creators
                    if "creators" in data:
                        for niche, accounts in data["creators"].items():
                            if niche not in combined["creators"]:
                                combined["creators"][niche] = []
                            combined["creators"][niche].extend(accounts)
                            
                except yaml.YAMLError as e:
                    logger.error(f"Failed to parse {cp}: {e}")
                    
        return combined

    def fetch(self) -> List[ContentItem]:
        """
        Open Instagram via Playwright, visit each creator's /reels/ page,
        extract shortcodes, prefetch metadata, and apply engagement filters.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("playwright not installed.")
            return []

        creators = self.watchlists.get("creators", {})
        if not creators:
            logger.info("No creators found in configurations.")
            return []

        items: List[ContentItem] = []
        filters = self.watchlists.get("filters", {})
        min_views = filters.get("min_views", 100000)
        min_likes = filters.get("min_likes", 5000)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context_kwargs = {
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "viewport": {"width": 1280, "height": 800},
            }
            
            proxy_url = os.environ.get("PROXY_SERVER")
            if proxy_url:
                context_kwargs["proxy"] = {"server": proxy_url}
                
            if self.session_file.exists():
                context_kwargs["storage_state"] = str(self.session_file)

            context = browser.new_context(**context_kwargs)
            page = context.new_page()

            api_reels = {} # shortcode -> {views, likes}
            
            def extract_reels(data):
                if isinstance(data, dict):
                    if "code" in data and "play_count" in data and isinstance(data["play_count"], int):
                        yield {
                            "shortcode": data["code"],
                            "views": data["play_count"],
                            "likes": data.get("like_count", 0),
                        }
                    for v in data.values():
                        yield from extract_reels(v)
                elif isinstance(data, list):
                    for item in data:
                        yield from extract_reels(item)

            def handle_res(response):
                if ("graphql" in response.url or "api/v1" in response.url) and response.request.resource_type in ["fetch", "xhr"]:
                    try:
                        text = response.text()
                        if "play_count" in text and "code" in text:
                            import json
                            data = json.loads(text)
                            for r in extract_reels(data):
                                if r["shortcode"] not in api_reels:
                                    api_reels[r["shortcode"]] = r
                    except Exception:
                        pass
                        
            page.on("response", handle_res)

            # Flatten to list of (niche, username) to process
            tasks = []
            for niche, accounts in creators.items():
                for acc in accounts:
                    tasks.append((niche, acc))
                    
            logger.info(f"Scanning {len(tasks)} creator profiles...")

            for niche, username in tasks:
                logger.info(f"Visiting profile: @{username} (niche: {niche})")
                
                try:
                    url = f"https://www.instagram.com/{username}/reels/"
                    page.goto(url, wait_until="domcontentloaded")
                    self._human_delay(2, 4)
                    
                    # Ensure page loaded correctly (look for reel links or standard IG markers)
                    try:
                        page.wait_for_selector("a[href*='/reel/']", timeout=10_000)
                    except Exception:
                        logger.debug(f"Could not find Reels tab for @{username} (might be private or empty).")
                        continue
                        
                    # Extract reel hrefs
                    links = page.locator("a[href*='/reel/']").all()
                    shortcodes = []
                    for link in links:
                        href = link.get_attribute("href")
                        if href:
                            # Extract shortcode from /reel/SHORTCODE/
                            parts = href.strip('/').split('/')
                            if len(parts) >= 2 and parts[-2] == "reel":
                                shortcodes.append(parts[-1])
                                
                    # Deduplicate shortcodes in this scrape
                    shortcodes = list(dict.fromkeys(shortcodes))
                    logger.info(f"Extracted {len(shortcodes)} shortcodes from @{username}")
                    
                    for shortcode in shortcodes:
                        reel_url = f"https://www.instagram.com/reel/{shortcode}/"
                        message_id = f"creator::{username}::{shortcode}"
                        
                        # Use DM dedup table to avoid re-processing same reel (we leverage the existing table)
                        if self.dedup.is_dm_seen(message_id):
                            continue
                            
                        # Standard visual/URL dedup check
                        temp_item = ContentItem(
                            url=reel_url,
                            platform=Platform.INSTAGRAM,
                            source_type=self.source_type,
                            niche=niche,
                        )
                        
                        if self.dedup.is_duplicate(temp_item):
                            self.dedup.register_dm(message_id, url, reel_url) # Mark seen so we don't query yt-dlp again
                            continue
                            
                        # Analyze engagement natively from our GraphQL interceptor!
                        if shortcode in api_reels:
                            views = api_reels[shortcode]["views"]
                            likes = api_reels[shortcode]["likes"]
                        else:
                            logger.warning(f"Could not find API metadata for {shortcode}, skipping.")
                            continue
                        
                        if views >= min_views and likes >= min_likes:
                            engagement_score = (views * 0.1) + (likes * 1.0)
                            
                            item = ContentItem(
                                url=reel_url,
                                platform=Platform.INSTAGRAM,
                                source_type=self.source_type,
                                niche=niche,
                                engagement_score=engagement_score,
                                view_count=views,
                                like_count=likes,
                                shortcode=shortcode,
                                raw_metadata={"creator": username, "source_profile": url}
                            )
                            items.append(item)
                            logger.info(f"✅ Found viral reel! @{username}/{shortcode} (Views: {views}, Likes: {likes})")
                            
                            # Register it as seen
                            self.dedup.register_dm(message_id, url, reel_url)
                        else:
                            # Not viral enough, still mark it as seen so we don't waste yt-dlp calls on it later
                            self.dedup.register_dm(message_id, url, reel_url)

                except Exception as e:
                    logger.error(f"Error scraping creator @{username}: {e}", exc_info=True)
                    
                self._human_delay(3, 6) # Delay between accounts

            browser.close()

        return items

    @staticmethod
    def _human_delay(min_s: float = 0.5, max_s: float = 2.0) -> None:
        time.sleep(random.uniform(min_s, max_s))
