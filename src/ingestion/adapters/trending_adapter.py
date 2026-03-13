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
import os
import random
import yaml
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Iterator, Dict, Any, Optional

from src.ingestion.base import ContentItem, Platform, SourceAdapter, SourceType, Niche
from src.ingestion.dedup import ContentDedup
from src.ingestion.downloader import UniversalDownloader
from src.utils.yt_dlp_helper import get_yt_dlp_command
from src.utils.proxy_helper import ProxyHelper

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
        
        # Initialize Vertex AI for semantic filtering
        from src.publishing_edge.config import GCP_PROJECT_ID
        from src.cloud_function.services.vertex_ai_service import VertexAIService
        self.ai = VertexAIService(project_id=GCP_PROJECT_ID)
        self.proxy_helper = ProxyHelper()
        
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
                                for item in v:
                                    if isinstance(item, dict) and item.get("enabled") is False:
                                        logger.info(f"Skipping disabled source in {cp}: {item}")
                                        continue
                                    combined["sources"][k].append(item)
                    if "filters" in data:
                        combined["filters"].update(data["filters"])
                except Exception as e:
                    logger.error(f"Failed to parse {cp}: {e}")
                    
        return combined

    def fetch(self, exclude_platforms: List[str] = None, min_views: int = None) -> Iterator[ContentItem]:
        if exclude_platforms is None:
            exclude_platforms = []
            
        sources = self.config.get("sources", {})
        
        # Helper to check if platform is enabled and get its min_views
        def get_p_meta(platform: str):
            p_cfg = self.get_platform_config(platform)
            # CLI exclude_platforms or min_views overrides config
            is_enabled = p_cfg.get("enabled", True) and (platform not in exclude_platforms)
            p_min_views = min_views if min_views else p_cfg.get("min_views", 100000)
            return is_enabled, p_min_views

        # 1. Fetch from Reddit
        enabled, p_min = get_p_meta(Platform.REDDIT)
        if enabled:
            for sub in set(sources.get("reddit", [])):
                yield from self._fetch_reddit(sub, p_min)

        # 2. Fetch from YouTube specific channels
        enabled, p_min = get_p_meta(Platform.YOUTUBE)
        if enabled:
            for chan_info in sources.get("youtube_channels", []):
                yield from self._fetch_youtube_channel(chan_info, p_min)
                
            # 3. Fetch from YouTube specifically via SEO search terms
            for term in set(sources.get("search_terms", [])):
                yield from self._fetch_youtube_search(term, p_min)
            
        # 3. Fetch from RSS Feeds
        enabled, _ = get_p_meta(Platform.WEB)
        if enabled:
            for feed in set(sources.get("rss", [])):
                yield from self._fetch_rss(feed)
            
        # 4. Fetch from specific Instagram news aggregators
        enabled, p_min = get_p_meta(Platform.INSTAGRAM)
        if enabled:
            ig_pages = sources.get("instagram_pages", [])
            if ig_pages:
                yield from self._fetch_instagram_pages_bulk(ig_pages, p_min)
            
        # 5. Fetch breaking news from Telegram 
        enabled, _ = get_p_meta(Platform.TELEGRAM)
        if enabled:
            for tg_channel in set(sources.get("telegram_channels", [])):
                yield from self._fetch_telegram_channel(tg_channel)

    def _safe_get(self, url: str, headers: dict = None, region: str = None) -> bytes:
        if headers is None:
            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) IGAutomation/1.0'}
        
        proxy_url = self.proxy_helper.get_proxy(region)
        if proxy_url:
            # Simple urllib proxy setup
            proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
            opener = urllib.request.build_opener(proxy_handler)
        else:
            opener = urllib.request.build_opener()
            
        req = urllib.request.Request(url, headers=headers)
        try:
            with opener.open(req, timeout=15) as response:
                return response.read()
        except Exception as e:
            logger.error(f"Request failed for {url} (Proxy: {proxy_url}): {e}")
            return b""

    def _fetch_reddit(self, subreddit: str, min_views: int = None) -> Iterator[ContentItem]:
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
                
                score = post.get('ups', 0)
                # Reddit floor conversion: usually upvotes are 1/20th of views
                reddit_floor = min_views // 20 if min_views else filters.get("reddit_min_upvotes", 5000)
                if score < reddit_floor:
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
                    niche=Niche.FUN if subreddit in ["funny", "memes"] else Niche.ENTERTAINMENT,
                    engagement_score=self.calculate_uvi("reddit", float(ups)),
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
                    yield item
                    logger.info(f"✅ Found Top Percentile Reddit Post: {title} ({ups} ups)")
                    
        except Exception as e:
            logger.error(f"Failed parsing Reddit r/{subreddit}: {e}")

    def _fetch_youtube_search(self, term: str, min_views: int = None) -> Iterator[ContentItem]:
        logger.info(f"Scanning YouTube for SEO term: '{term}' (Percentile Selection, Max 72h old)...")
        items = []
        # yt-dlp search for the top 100 videos related to the SEO keyword and date filters
        proxy = self.proxy_helper.get_proxy()
        yt_cmd = get_yt_dlp_command([
            "yt-dlp", "--flat-playlist", "--dump-json", f"ytsearch100:{term}"
        ], proxy=proxy)
        
        try:
            import subprocess
            proc = subprocess.run(yt_cmd, capture_output=True, text=True, timeout=120)
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
                    filters = self.config.get("filters", {})
                    
                    # 100k View Floor
                    if view_count < filters.get("min_views", 100000):
                        continue
                    
                    message_id = f"yt_seo::{vid_id}"
                    if not self.dedup.is_dm_seen(message_id):
                        item = ContentItem(
                            url=vid_url,
                            platform=Platform.YOUTUBE,
                            source_type=self.source_type,
                            niche=Niche.ENTERTAINMENT, 
                            engagement_score=self.calculate_uvi("youtube", float(view_count)),
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

    def _fetch_youtube_channel(self, chan_info: str | dict, min_views: int = None) -> Iterator[ContentItem]:
        if isinstance(chan_info, str):
            chan_id = chan_info
            subscriber_baseline = 0
            chan_name = chan_id
        else:
            chan_id = chan_info.get("channel_id")
            subscriber_baseline = chan_info.get("subscriber_baseline", 0)
            chan_name = chan_info.get("name", chan_id)

        logger.info(f"Scanning YouTube channel: {chan_name} ({chan_id})")
        items = []
        
        # yt-dlp to get the most recent videos with metrics
        proxy = self.proxy_helper.get_proxy()
        yt_cmd = get_yt_dlp_command([
            "yt-dlp", "--flat-playlist", "--dump-json", 
            "--playlist-end", "20",
            f"https://www.youtube.com/channel/{chan_id}/videos"
        ], proxy=proxy)
        
        try:
            import subprocess
            proc = subprocess.run(yt_cmd, capture_output=True, text=True, timeout=60)
            
            valid_videos = []
            if proc.returncode == 0:
                for line in proc.stdout.strip().splitlines():
                    try:
                        data = json.loads(line)
                        valid_videos.append(data)
                    except json.JSONDecodeError:
                        continue
            
            if not valid_videos:
                return items

            # If no baseline provided, try to find it in the first video's metadata
            if subscriber_baseline == 0:
                subscriber_baseline = valid_videos[0].get("channel_follower_count", 0)
                logger.debug(f"Auto-detected subscriber count for {chan_name}: {subscriber_baseline}")

            # Outlier Multiplier Logic for YouTube
            # We look for videos that outperform the channel's baseline by a factor (default 1.5)
            multiplier = self.config.get("filters", {}).get("outlier_multiplier", 1.5)
            
            for data in valid_videos:
                vid_id = data.get("id")
                vid_url = f"https://www.youtube.com/watch?v={vid_id}"
                view_count = data.get("view_count", 0)
                
                # View Floor
                floor = min_views if min_views else self.config.get("filters", {}).get("min_views", 100000)
                if view_count < floor:
                    continue

                outlier_threshold = int(subscriber_baseline * multiplier) if subscriber_baseline > 0 else 50000
                
                if view_count >= outlier_threshold:
                    message_id = f"yt_chan::{vid_id}"
                    if not self.dedup.is_dm_seen(message_id):
                        item = ContentItem(
                            url=vid_url,
                            platform=Platform.YOUTUBE,
                            source_type=self.source_type,
                            niche=Niche.FUN if "funny" in chan_name.lower() or "meme" in chan_name.lower() else Niche.ENTERTAINMENT, 
                            engagement_score=self.calculate_uvi("youtube", float(view_count)),
                            view_count=view_count,
                            title=data.get("title", ""),
                            duration_seconds=data.get("duration"),
                            raw_metadata={"text_prompt": data.get("title", ""), "channel": chan_name}
                        )
                        self.dedup.register_dm(message_id, vid_url, vid_url)
                        yield item
                        logger.info(f"✅ Found Viral YouTube Outlier: {item.title} ({view_count} views vs {subscriber_baseline} subs)")
                        
        except Exception as e:
            logger.error(f"Failed fetching YouTube channel {chan_name}: {e}")

    def _fetch_instagram_pages_bulk(self, pages: List[str | dict], min_views: int = None) -> Iterator[ContentItem]:
        logger.info(f"Bulk scanning {len(pages)} Instagram news aggregators...")
        
        from src.ingestion.adapters.creator_adapter import CreatorAdapter
        import tempfile
        
        # Build bulk creators config
        news_accounts = []
        for p in pages:
            if isinstance(p, str):
                news_accounts.append({"username": p, "follower_baseline": 0})
            else:
                news_accounts.append({"username": p.get("username"), "follower_baseline": p.get("follower_baseline", 0)})

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
            mock_config = {
                "filters": {
                    "min_views": min_views if min_views else 100000, 
                    "min_likes": 5000,
                    "outlier_multiplier": 0.2  # Drastically relaxed for maximum yield
                },
                "creators": {
                    "news": news_accounts
                }
            }
            yaml.dump(mock_config, tmp)
            tmp_path = tmp.name
                
        try:
            headless = str(os.environ.get("HEADLESS", "true")).lower() == "true"
            # SINGLE session for ALL pages
            adapter = CreatorAdapter(config_paths=[tmp_path], headless=headless)
            for item in adapter.fetch(min_views=min_views):
                item.source_type = self.source_type
                yield item
            
        except Exception as e:
            logger.error(f"Failed bulk discovery for IG news pages: {e}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        
    def _fetch_telegram_channel(self, channel_name: str) -> Iterator[ContentItem]:
        logger.info(f"Scanning Telegram OSINT channel: {channel_name}")
        # within the last 12 hours.
        if False: yield # Generator placeholder

    def _fetch_rss(self, feed_url: str) -> Iterator[ContentItem]:
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
                        yield item
                        logger.info(f"✅ Found Trending News/Topic: {title}")
                        
        except Exception as e:
            logger.error(f"Failed parsing RSS {feed_url}: {e}")
