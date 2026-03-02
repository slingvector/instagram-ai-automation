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
GENERIC_BROLL_URL = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"  # Big Buck Bunny 60fps 4K as a safe placeholder

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
                "youtube": [],
                "rss": []
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
            
        # 2. Fetch from YouTube Trending
        if sources.get("youtube"):
            items.extend(self._fetch_youtube_trending())
            
        # 3. Fetch from RSS Feeds
        for feed in set(sources.get("rss", [])):
            items.extend(self._fetch_rss(feed))
            
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
        logger.info(f"Scanning Reddit r/{subreddit}...")
        min_upvotes = self.config.get("filters", {}).get("reddit_min_upvotes", 20000)
        items = []
        
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=25"
        data_bytes = self._safe_get(url)
        if not data_bytes:
            return items
            
        try:
            data = json.loads(data_bytes.decode('utf-8'))
            children = data.get('data', {}).get('children', [])
            
            for child in children:
                post = child.get('data', {})
                ups = post.get('ups', 0)
                
                if ups < min_upvotes:
                    continue
                    
                post_url = "https://www.reddit.com" + post.get('permalink', '')
                title = post.get('title', '')
                is_video = post.get('is_video', False)
                content_url = post.get('url', post_url)
                
                # If it's a native Reddit video, yt-dlp can handle the post permalink.
                # If it's pure text, we assign the generic B-roll.
                target_url = post_url if is_video else GENERIC_BROLL_URL
                
                item = ContentItem(
                    url=target_url,
                    platform=Platform.REDDIT,
                    source_type=self.source_type,
                    niche=Niche.ENTERTAINMENT if subreddit in ["all", "funny"] else Niche.FUN,
                    engagement_score=ups * 1.0,
                    view_count=ups, # treating upvotes as views for ranking
                    like_count=ups,
                    title=title,
                    raw_metadata={
                        "reddit_post_url": post_url,
                        "content_url": content_url,
                        "is_video": is_video,
                        "text_prompt": title # For text burn-in
                    }
                )
                
                # Use a specific dedup key across Reddit
                message_id = f"reddit::{post.get('id')}"
                if not self.dedup.is_dm_seen(message_id):
                    self.dedup.register_dm(message_id, post_url, target_url)
                    items.append(item)
                    logger.info(f"✅ Found Viral Reddit Post: {title} ({ups} upvotes)")
                    
        except Exception as e:
            logger.error(f"Failed parsing Reddit r/{subreddit}: {e}")
            
        return items

    def _fetch_youtube_trending(self) -> List[ContentItem]:
        logger.info("Scanning YouTube Trending...")
        items = []
        # yt-dlp can dump the trending feed playlist
        cmd = ["yt-dlp", "--flat-playlist", "--dump-json", "https://www.youtube.com/feed/trending"]
        try:
            import subprocess
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if proc.returncode == 0:
                for line in proc.stdout.strip().splitlines():
                    try:
                        data = json.loads(line)
                        vid_id = data.get("id")
                        vid_url = f"https://www.youtube.com/watch?v={vid_id}"
                        view_count = data.get("view_count", 0)
                        
                        # Apply naive filter (1M views for YT trending)
                        if view_count and int(view_count) > 1000000:
                            message_id = f"yt_trending::{vid_id}"
                            if not self.dedup.is_dm_seen(message_id):
                                item = ContentItem(
                                    url=vid_url,
                                    platform=Platform.YOUTUBE,
                                    source_type=self.source_type,
                                    niche=Niche.ENTERTAINMENT,
                                    engagement_score=int(view_count) * 0.1,
                                    view_count=int(view_count),
                                    title=data.get("title", ""),
                                    duration_seconds=data.get("duration"),
                                    raw_metadata={"text_prompt": data.get("title", "")}
                                )
                                self.dedup.register_dm(message_id, vid_url, vid_url)
                                items.append(item)
                                logger.info(f"✅ Found YT Trending: {item.title} ({item.view_count} views)")
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Failed fetching YouTube Trending via yt-dlp: {e}")
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
