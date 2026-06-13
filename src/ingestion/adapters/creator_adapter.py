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
from typing import List, Iterator, Optional, Dict, Any

from src.ingestion.base import ContentItem, Platform, SourceAdapter, SourceType
from src.ingestion.dedup import ContentDedup
from src.ingestion.downloader import UniversalDownloader
from src.utils.proxy_helper import ProxyHelper

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
        self.proxy_helper = ProxyHelper()
        self.watchlists = self._load_configs()

    def _load_configs(self) -> dict:
        combined = {
            "filters": {
                "min_views": 500000,
                "min_likes": 10000,
                "outlier_multiplier": 1.5,
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

    def fetch(self, min_views: int = None, broad_mode: bool = False) -> Iterator[ContentItem]:
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
        
        p_cfg = self.get_platform_config(Platform.INSTAGRAM)
        if not p_cfg.get("enabled", True):
            logger.warning("Instagram platform is disabled in uvi_config.yaml. Skipping CreatorAdapter fetch.")
            return items

        filters = self.watchlists.get("filters", {})
        min_views_internal = min_views if min_views else p_cfg.get("min_views", 100000)
        min_likes = filters.get("min_likes", 5000)

        with sync_playwright() as p:
            persistent_dir = Path("data/browser_session")
            persistent_dir.mkdir(parents=True, exist_ok=True)
            
            context_kwargs = {
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "viewport": {"width": 1280, "height": 800},
                "headless": self.headless,
            }
            
            proxy_config = self.proxy_helper.get_playwright_proxy()
            if proxy_config:
                context_kwargs["proxy"] = proxy_config

            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(persistent_dir),
                    **context_kwargs
                )
            except Exception as e:
                logger.warning(f"Failed to launch persistent context: {e}. Falling back to standard non-persistent launch.")
                # Remove user_data_dir and launch regular browser
                browser = p.chromium.launch(headless=self.headless, proxy=context_kwargs.get("proxy"))
                context = browser.new_context(user_agent=context_kwargs["user_agent"], viewport=context_kwargs["viewport"])
            
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
                        
            tasks = []
            for niche, accounts in creators.items():
                for acc in accounts:
                    if isinstance(acc, str):
                        tasks.append((niche, {"username": acc}))
                    elif isinstance(acc, dict):
                        tasks.append((niche, acc))
            
            # Increase diversity by shuffling tasks
            random.shuffle(tasks)
            logger.info(f"Scanning {len(tasks)} creator profiles (shuffled for diversity)...")

            for niche, acc_info in tasks:
                if "username" in acc_info:
                    username = acc_info["username"]
                    display_name = f"@{username}"
                    url = f"https://www.instagram.com/{username}/reels/"
                elif "hashtag" in acc_info:
                    hashtag = acc_info["hashtag"]
                    display_name = f"#{hashtag}"
                    url = f"https://www.instagram.com/explore/tags/{hashtag}/"
                else:
                    continue

                follower_baseline = acc_info.get("follower_baseline", 0)
                is_private = acc_info.get("is_private", False)
                
                logger.info(f"Visiting target: {display_name} (niche: {niche})")
                
                page = None
                try:
                    # Create a fresh page for each target to prevent Timeout cascades
                    page = context.new_page()
                    page.on("response", handle_res)
                    
                    page.goto(url, wait_until="domcontentloaded")
                    self._human_delay(2, 4)
                    
                    if follower_baseline == 0 and "username" in acc_info:
                        follower_baseline = self._get_follower_count(page)
                    logger.info(f"Target {display_name} mapped with {follower_baseline} followers/baseline.")
                    
                    # Ensure page loaded correctly (look for reel/p links)
                    try:
                        page.wait_for_selector("a[href*='/reel/'], a[href*='/p/']", timeout=10_000)
                    except Exception:
                        logger.debug(f"Could not find Reels/Posts for {display_name} (might be private, empty, or rate limited).")
                        continue
                        
                    # Extract reel hrefs with scrolling for deeper yield
                    shortcodes = []
                    for _ in range(50): # Scroll 50 times for massive hashtag yield (thousands of videos)
                        links = page.locator("a[href*='/reel/'], a[href*='/p/']").all()
                        for link in links:
                            href = link.get_attribute("href")
                            if href:
                                parts = href.strip('/').split('/')
                                if len(parts) >= 2 and parts[-2] in ("reel", "p"):
                                    shortcodes.append(parts[-1])
                        page.mouse.wheel(0, 3000)
                        self._human_delay(1, 2)
                                
                    # Deduplicate shortcodes in this scrape
                    shortcodes = list(dict.fromkeys(shortcodes))
                    logger.info(f"Extracted {len(shortcodes)} shortcodes from @{username} (after scrolling)")
                    
                    yielded_for_this_account = 0
                    
                    for shortcode in shortcodes:
                        if yielded_for_this_account >= 50:
                            logger.info(f"Reached max limit of 50 reels for {display_name}, moving to next account.")
                            break
                            
                        reel_url = f"https://www.instagram.com/reel/{shortcode}/"
                        message_id = f"target::{display_name}::{shortcode}"
                        
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
                        if broad_mode:
                            # In broad mode, we don't care about API metadata (views/likes) yet.
                            # We just want to populate the SCANNED queue.
                            yield temp_item
                            yielded_for_this_account += 1
                            continue
                            
                        if shortcode in api_reels:
                            views = api_reels[shortcode]["views"]
                            likes = api_reels[shortcode]["likes"]
                        else:
                            logger.warning(f"Could not find API metadata for {shortcode}, skipping.")
                            continue
                        
                        # Outlier Multiplier Logic: The view count must exceed either the global minimum OR
                        # the creator's follower count multiplied by the outlier factor.
                        # For massive accounts (e.g. 70M), we cap the baseline influence to avoid impossible thresholds.
                        capped_baseline = min(follower_baseline, 2_000_000) 
                        multiplier = filters.get("outlier_multiplier", 1.5)
                        outlier_threshold = max(min_views_internal, int(capped_baseline * multiplier)) if capped_baseline > 0 else min_views_internal
                        
                        logger.debug(f"Evaluating {shortcode} - Views: {views}. Required Outlier Threshold: {outlier_threshold}")
                        
                        if views >= outlier_threshold and likes >= min_likes:
                            engagement_score = self.calculate_uvi("instagram", float(views))
                            
                            item = ContentItem(
                                url=reel_url,
                                platform=Platform.INSTAGRAM,
                                source_type=self.source_type,
                                niche=niche,
                                engagement_score=engagement_score,
                                view_count=views,
                                like_count=likes,
                                shortcode=shortcode,
                                raw_metadata={"source_target": display_name, "source_profile": url}
                            )
                            # ONLY register in dedup if we are actually yielding it as a hit
                            self.dedup.register_dm(message_id, url, reel_url)
                            yield item
                            yielded_for_this_account += 1
                            logger.info(f"✅ Found viral reel! {display_name}/{shortcode} (Views: {views}, Likes: {likes})")
                        else:
                            # Not viral enough. We DON'T register in dedup here so that if the user 
                            # lowers thresholds later, we can still discover it.
                            pass

                except Exception as e:
                    logger.error(f"Error scraping target {display_name}: {e}")
                finally:
                    if page:
                        try:
                            page.close()
                        except Exception:
                            pass
                    
                self._human_delay(3, 6) # Delay between accounts

            # Close any dangling pages
            for p in context.pages:
                try:
                    p.close()
                except Exception:
                    pass
            context.close()

    @staticmethod
    def _get_follower_count(page) -> int:
        """Parse the creator's follower count right off the Instagram page title/meta description."""
        try:
            content = page.evaluate("""() => {
                let meta = document.querySelector('meta[name="description"]');
                return meta ? meta.content : "";
            }""")
            if content:
                import re
                m = re.search(r'([\d\.,]+[kKmM]?)\s+Followers', content, re.IGNORECASE)
                if m:
                    val_str = m.group(1).upper().replace(',', '')
                    if 'M' in val_str:
                        return int(float(val_str.replace('M', '')) * 1000000)
                    elif 'K' in val_str:
                        return int(float(val_str.replace('K', '')) * 1000)
                    else:
                        return int(val_str)
        except Exception as e:
            logger.debug(f"Could not parse follower count: {e}")
        return 0

    @staticmethod
    def _human_delay(min_s: float = 0.5, max_s: float = 2.0) -> None:
        time.sleep(random.uniform(min_s, max_s))
