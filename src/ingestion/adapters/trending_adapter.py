"""
src/ingestion/adapters/trending_adapter.py

UC3: Real-Time Trending Monitor
Fetches viral trends from Reddit, YouTube Trending, and RSS feeds.
Outputs ContentItem instances. For text-only trends (e.g. RSS news), 
it injects a generic B-roll video URL so the downstream media factory 
can process and burn the trend text onto the video.
"""
from __future__ import annotations

import logging
import json
import random
import yaml
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

from src.ingestion.base import ContentItem, Platform, SourceAdapter, SourceType, Niche
from src.ingestion.dedup import ContentDedup
from src.ingestion.downloader import UniversalDownloader

logger = logging.getLogger(__name__)

# Fallback open-source/creative-commons or generic IG-friendly B-roll video
# In production, this would be selected dynamically from a local asset vault.
GENERIC_BROLL_URL = "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/1080/Big_Buck_Bunny_1080_10s_1MB.mp4"

class TrendingAdapter(SourceAdapter):
    source_type = SourceType.TRENDING

    def __init__(self, config_paths: List[str] = None):
        if config_paths is None:
            config_paths = ["config/trending_sources.yaml"]
            
        self.config_paths = [Path(p) for p in config_paths]
        self.dedup = ContentDedup()
        self.downloader = UniversalDownloader(output_dir=Path("data/downloads/tmp"))
        self.config = self._load_configs()
        
    def _load_configs(self) -> dict:
        combined = {
            "sources": {
                "reddit": [],
                "youtube_channels": [],
                "rss": [],
                "telegram_channels": [],
                "instagram_pages": [],
                "search_terms": [],
                "hashtags": []
            },
            "filters": {
                "reddit_min_upvotes": 20000
            }
        }
        
        for cp in self.config_paths:
            if not cp.exists():
                logger.warning(f"Trending config not found: {cp}")
                continue
            with open(cp, "r", encoding="utf-8") as f:
                try:
                    data = yaml.safe_load(f) or {}
                    if "sources" in data:
                        for k, v in data["sources"].items():
                            if k in combined["sources"] and isinstance(v, list):
                                combined["sources"][k].extend(v)
                    if "filters" in data:
                        combined["filters"].update(data["filters"])
                except Exception as e:
                    logger.error(f"Failed to parse {cp}: {e}")
                    
        return combined

    def fetch(self) -> List[ContentItem]:
        items: List[ContentItem] = []
        sources = self.config.get("sources", {})
        
        # 1. Fetch from Reddit
        for sub in set(sources.get("reddit", [])):
            items.extend(self._fetch_reddit(sub))
            
        # 2. Fetch from YouTube specifically via SEO search terms
        for term in set(sources.get("search_terms", [])):
            items.extend(self._fetch_youtube_search(term))
            
        # 3. Fetch from RSS Feeds
        for feed in set(sources.get("rss", [])):
            items.extend(self._fetch_rss(feed))
            
        # 4. Fetch from specific Instagram news aggregators
        for ig_page in set(sources.get("instagram_pages", [])):
            items.extend(self._fetch_instagram_page(ig_page))
            
        # 5. Fetch breaking news from Telegram 
        for tg_channel in set(sources.get("telegram_channels", [])):
            items.extend(self._fetch_telegram_channel(tg_channel))
            
        return items

    def _safe_get(self, url: str, headers: dict = None) -> bytes:
        if headers is None:
            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) IGAutomation/1.0'}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read()
        except Exception as e:
            logger.error(f"Request failed for {url}: {e}")
            return b""

    def _fetch_reddit(self, subreddit: str) -> List[ContentItem]:
        logger.info(f"Scanning Reddit r/{subreddit} (Percentile Selection, 24-72h)...")
        items = []
        
        # Pull larger quota for percentile selection
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=100"
        data_bytes = self._safe_get(url)
        if not data_bytes:
            return items
            
        try:
            data = json.loads(data_bytes.decode('utf-8'))
            children = data.get('data', {}).get('children', [])
            
            import time
            current_time = time.time()
            # Between 24 and 72 hours old
            min_age = current_time - (24 * 3600)
            max_age = current_time - (72 * 3600)
            
            valid_posts = []
            for child in children:
                post = child.get('data', {})
                created_utc = post.get('created_utc', 0)
                
                # Check 24-72h window
                if created_utc > min_age or created_utc < max_age:
                    continue
                
                score = post.get('ups', 0) # Assuming 'ups' is the score
                if score < 500 and not post.get("is_original_content", False):
                    continue
                    
                valid_posts.append(post)
                
            if not valid_posts:
                return items
                
            # Percentile Selection: Top 10%
            valid_posts.sort(key=lambda x: x.get('ups', 0), reverse=True)
            top_count = max(1, int(len(valid_posts) * 0.10))
            top_posts = valid_posts[:top_count]
            
            for post in top_posts:
                title = post.get('title', '')
                ups = post.get('ups', 0)
                is_video = post.get('is_video', False)
                post_url = "https://www.reddit.com" + post.get('permalink', '')
                content_url = post.get('url', post_url)
                
                target_url = post_url if is_video else GENERIC_BROLL_URL
                
                item = ContentItem(
                    url=target_url,
                    platform=Platform.REDDIT,
                    source_type=self.source_type,
                    niche=Niche.ENTERTAINMENT if subreddit in ["all", "funny"] else Niche.FUN,
                    engagement_score=float(ups), # Score stored raw, weighted at pipeline level
                    view_count=ups,
                    like_count=ups,
                    title=title,
                    raw_metadata={
                        "reddit_post_url": post_url,
                        "content_url": content_url,
                        "is_video": is_video,
                        "text_prompt": title
                    }
                )
                
                message_id = f"reddit::{post.get('id')}"
                if not self.dedup.is_dm_seen(message_id):
                    self.dedup.register_dm(message_id, post_url, target_url)
                    items.append(item)
                    logger.info(f"✅ Found Top Percentile Reddit Post: {title} ({ups} ups)")
                    
        except Exception as e:
            logger.error(f"Failed parsing Reddit r/{subreddit}: {e}")
            
        return items

    def _fetch_youtube_search(self, term: str) -> List[ContentItem]:
        logger.info(f"Scanning YouTube for SEO term: '{term}' (Percentile Selection, Max 72h old)...")
        items = []
        # yt-dlp search for the top 50 videos related to the SEO keyword and date filters
        cmd = ["yt-dlp", "--flat-playlist", "--dump-json", "--dateafter", "today-3days", f"ytsearch50:{term}"]
        try:
            import subprocess
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if proc.returncode == 0:
                valid_videos = []
                for line in proc.stdout.strip().splitlines():
                    try:
                        data = json.loads(line)
                        vid_id = data.get("id")
                        if not vid_id:
                            continue
                            
                        duration = data.get("duration", 0)
                        if duration and duration > 3600:
                            continue # skip massive hour-long streams
                            
                        # yt-dlp dateafter handles recency, collect valid items
                        valid_videos.append(data)
                    except json.JSONDecodeError:
                        continue
                        
                if not valid_videos:
                    return items
                    
                # Percentile selection (Top 10%)
                valid_videos.sort(key=lambda x: x.get('view_count', 0), reverse=True)
                top_count = max(1, int(len(valid_videos) * 0.10))
                top_videos = valid_videos[:top_count]
                
                for data in top_videos:
                    vid_id = data.get("id")
                    vid_url = f"https://www.youtube.com/watch?v={vid_id}"
                    view_count = data.get("view_count", 0)
                    
                    message_id = f"yt_seo::{vid_id}"
                    if not self.dedup.is_dm_seen(message_id):
                        item = ContentItem(
                            url=vid_url,
                            platform=Platform.YOUTUBE,
                            source_type=self.source_type,
                            niche=Niche.ENTERTAINMENT, 
                            engagement_score=float(view_count),
                            view_count=view_count,
                            title=data.get("title", ""),
                            duration_seconds=data.get("duration"),
                            raw_metadata={"text_prompt": data.get("title", ""), "seo_term": term}
                        )
                        self.dedup.register_dm(message_id, vid_url, vid_url)
                        items.append(item)
                        logger.info(f"✅ Found Top Percentile SEO YT Hit ['{term}']: {item.title} ({item.view_count} views)")

        except Exception as e:
            logger.error(f"Failed fetching YouTube SEO terms via yt-dlp: {e}")
        return items

    def _fetch_instagram_page(self, page_name: str) -> List[ContentItem]:
        logger.info(f"Scanning specific Instagram news page: {page_name}")
        items = []
        try:
            from src.ingestion.adapters.creator_adapter import CreatorAdapter
            import tempfile
            
            # Create a temporary config to target just this news page with relaxed viral thresholds
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
                mock_config = {
                    "filters": {"min_views": 100000, "min_likes": 5000},
                    "creators": {"news": [page_name]}
                }
                yaml.dump(mock_config, tmp)
                tmp_path = tmp.name
                
            try:
                # Instantiate and run the CreatorAdapter securely on the temporary config
                headless = str(os.environ.get("HEADLESS", "true")).lower() == "true"
                adapter = CreatorAdapter(config_paths=[tmp_path], headless=headless)
                items = adapter.fetch()
                
                # Update source_type to reflect it was found via Trending pipeline
                for item in items:
                    item.source_type = self.source_type
                    
            finally:
                import os
                os.remove(tmp_path)
                
        except Exception as e:
            logger.error(f"Failed standing up CreatorAdapter instance for IG page {page_name}: {e}")
            
        return items
        
    def _fetch_telegram_channel(self, channel_name: str) -> List[ContentItem]:
        logger.info(f"Scanning Telegram OSINT channel: {channel_name}")
        items = []
        # TODO: Implement Telethon-based scraping looking for highest viewed MP4s in the channel
        # within the last 12 hours.
        return items

    def _fetch_rss(self, feed_url: str) -> List[ContentItem]:
        logger.info(f"Scanning RSS feed: {feed_url}")
        items = []
        xml_bytes = self._safe_get(feed_url)
        if not xml_bytes:
            return items
            
        try:
            root = ET.fromstring(xml_bytes)
            # Find all item elements
            for item_elem in root.findall(".//item"):
                title_elem = item_elem.find("title")
                link_elem = item_elem.find("link")
                
                if title_elem is not None and link_elem is not None:
                    title = title_elem.text
                    link = link_elem.text
                    
                    if not title or not link:
                        continue
                        
                    # Extract ID from link / guid
                    guid_elem = item_elem.find("guid")
                    guid = guid_elem.text if guid_elem is not None else link
                    
                    # Dedup check
                    import hashlib
                    guid_hash = hashlib.md5(guid.encode('utf-8')).hexdigest()
                    message_id = f"rss::{guid_hash}"
                    
                    if not self.dedup.is_dm_seen(message_id):
                        item = ContentItem(
                            url=GENERIC_BROLL_URL,
                            platform=Platform.WEB,
                            source_type=self.source_type,
                            niche=Niche.ENTERTAINMENT,
                            title=title,
                            raw_metadata={
                                "rss_link": link,
                                "text_prompt": title # Important for the media factory to overlay the text
                            }
                        )
                        self.dedup.register_dm(message_id, link, GENERIC_BROLL_URL)
                        items.append(item)
                        logger.info(f"✅ Found Trending News/Topic: {title}")
                        
        except Exception as e:
            logger.error(f"Failed parsing RSS {feed_url}: {e}")
            
        return items
