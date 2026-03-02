"""
src/ingestion/adapters/cross_platform_adapter.py

UC4: Cross-Platform Content Adapter
Uses yt-dlp to scrape and ingest videos from TikTok, YT Shorts, Snapchat, Facebook Reels, and X.
Loads target accounts/hashtags from config/cross_platform.yaml.
"""
from __future__ import annotations

import logging
import os
import yaml
from pathlib import Path
from typing import List

from src.ingestion.base import ContentItem, Platform, SourceAdapter, SourceType
from src.ingestion.dedup import ContentDedup
from src.ingestion.downloader import UniversalDownloader

logger = logging.getLogger(__name__)

# Used if yaml mapping isn't explicitly defined
_DEFAULT_NICHE = "entertainment"

class CrossPlatformAdapter(SourceAdapter):
    """
    Reads config/cross_platform.yaml and queries yt-dlp to find new videos
    from specified multi-platform creators or hashtags.
    """
    source_type = SourceType.CROSS_PLATFORM

    def __init__(self, config_path: str = "config/cross_platform.yaml", max_items_per_query: int = 5):
        self.config_path = Path(config_path)
        self.max_items_per_query = max_items_per_query
        self.dedup = ContentDedup()
        
        # We need the downloader just for its prefetch_metadata capability
        # The actual download happens dynamically when scheduler.py triggers
        self.downloader = UniversalDownloader(output_dir=Path("data/downloads/tmp"))
        self.targets = self._load_config()

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            logger.warning(f"Cross-platform config not found: {self.config_path}")
            return {}
            
        with open(self.config_path, "r", encoding="utf-8") as f:
            try:
                return yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                logger.error(f"Failed to parse {self.config_path}: {e}")
                return {}

    def fetch(self) -> List[ContentItem]:
        """Iterates through all platforms and niches in the config and returns newly discovered content."""
        items: List[ContentItem] = []
        
        for platform_key, niches in self.targets.items():
            platform_enum = self._map_platform_key(platform_key)
            
            if not isinstance(niches, dict):
                continue
                
            for niche, queries in niches.items():
                if not isinstance(queries, list):
                    continue
                    
                for query in queries:
                    logger.info(f"Checking {platform_key} for {query} (niche: {niche})")
                    try:
                        results = self._fetch_for_query(platform_enum, niche, query)
                        items.extend(results)
                    except Exception as e:
                        logger.error(f"Failed to fetch {query} on {platform_key}: {e}", exc_info=True)
                        
        return items

    def _map_platform_key(self, key: str) -> str:
        key = key.lower()
        if "tiktok" in key: return Platform.TIKTOK
        if "youtube" in key: return Platform.YOUTUBE
        if "snapchat" in key: return Platform.SNAPCHAT
        if "facebook" in key: return Platform.FACEBOOK
        if "twitter" in key or "x" in key: return Platform.TWITTER
        if "telegram" in key: return Platform.TELEGRAM
        return Platform.WEB

    def _construct_ytdlp_url(self, platform: str, query: str) -> str:
        """Translates a yaml query (like '@wisdm' or '#mensfashion') into a scrapeable URL."""
        if platform == Platform.TIKTOK:
            if query.startswith("@"):
                return f"https://www.tiktok.com/{query}"
            elif query.startswith("#"):
                return f"https://www.tiktok.com/tag/{query[1:]}"
                
        elif platform == Platform.YOUTUBE:
            if query.startswith("@"):
                return f"https://www.youtube.com/{query}/shorts"
            return f"ytsearch{self.max_items_per_query}:{query} shorts"
            
        # Add basic fallback for raw URLs
        if query.startswith("http"):
             return query
             
        # Fallback search
        return f"ytsearch{self.max_items_per_query}:{query}"

    def _fetch_for_query(self, platform: str, niche: str, query: str) -> List[ContentItem]:
        target_url = self._construct_ytdlp_url(platform, query)
        items: List[ContentItem] = []
        
        # Use yt-dlp to extract a flat playlist of videos up to our limit
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--dump-json",
            "--playlist-end", str(self.max_items_per_query),
            "--no-warnings",
            "--ignore-errors",
            target_url
        ]
        
        import subprocess
        import json
        
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if not proc.stdout.strip():
                return []
                
            for line in proc.stdout.strip().split("\n"):
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    url = data.get("url") or data.get("webpage_url")
                    if not url: continue
                    
                    # Synthesize full url if relative
                    if url.startswith("/") and platform == Platform.TIKTOK:
                        url = f"https://www.tiktok.com{url}"
                        
                    # Skip if we already downloaded this URL anywhere
                    from urllib.parse import urlparse, urlunparse
                    p = urlparse(url)
                    canonical_url = urlunparse((p.scheme, p.netloc, p.path, '', '', ''))
                    
                    # Create a temporary item just for dedup checking to avoid prefetching metadata on seen items
                    temp_item_for_dedup = ContentItem(
                        url=canonical_url,
                        platform=platform,
                        source_type=self.source_type,
                        niche=niche,
                    )
                    
                    if self.dedup.is_duplicate(temp_item_for_dedup):
                         continue

                    # Prefetch full engagement info via the Universal Downloader
                    meta = self.downloader.prefetch_metadata(url)
                    
                    engagement_score = 0.0
                    views = meta.get("view_count", 0)
                    likes = meta.get("like_count", 0)
                    title = meta.get("title", data.get("title", ""))
                    
                    if views > 0 or likes > 0:
                        engagement_score = (views * 0.1) + (likes * 1.0)
                        
                    item = ContentItem(
                        url=url,
                        platform=platform,
                        source_type=self.source_type,
                        niche=niche,
                        engagement_score=engagement_score,
                        view_count=views,
                        like_count=likes,
                        title=title[:200] if title else None,
                        duration_seconds=meta.get("duration"),
                        raw_metadata={"query": query, "original_extractor": data.get("extractor")}
                    )
                    items.append(item)
                except json.JSONDecodeError:
                    continue
                    
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout while scanning {target_url}")
        except Exception as e:
            logger.error(f"Error scanning {target_url}: {e}", exc_info=True)
            
        return items
