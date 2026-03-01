"""
src/ingestion/adapters/cross_platform_adapter.py

UC4: Cross-Platform Content Adapter
Downloads top-performing content from YouTube Shorts, TikTok, Snapchat, Facebook Reels,
and Telegram using yt-dlp (handles all platforms natively).

Config: config/cross_platform.yaml
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

import yaml

from src.ingestion.base import ContentItem, Niche, Platform, SourceAdapter, SourceType, AccountProfile
from src.ingestion.downloader import UniversalDownloader

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parents[3] / "config" / "cross_platform.yaml"
_DOWNLOAD_DIR = Path("data/downloads/cross_platform")


class CrossPlatformAdapter(SourceAdapter):
    """
    Iterates a YAML watchlist of accounts/channels per platform,
    prefetches engagement metadata via yt-dlp, filters by threshold,
    and returns ContentItems for qualifying videos.
    """

    source_type = SourceType.CROSS_PLATFORM

    def __init__(self):
        self.downloader = UniversalDownloader(output_dir=_DOWNLOAD_DIR)
        self.config = self._load_config()

    def fetch(self) -> List[ContentItem]:
        items: List[ContentItem] = []
        for platform_key, platform_cfg in self.config.get("platforms", {}).items():
            if not platform_cfg.get("enabled", True):
                continue
            platform_id = _PLATFORM_MAP.get(platform_key, Platform.WEB)
            for account in platform_cfg.get("accounts", []):
                url  = account.get("url", "")
                niche = account.get("niche", Niche.ENTERTAINMENT)
                filters = platform_cfg.get("filters", {})
                if not url:
                    continue
                try:
                    fetched = self._fetch_account(url, platform_id, niche, filters)
                    items.extend(fetched)
                except Exception as e:
                    logger.warning(f"CrossPlatform fetch failed for {url}: {e}")
        return items

    def _fetch_account(self, url: str, platform: str, niche: str, filters: dict) -> List[ContentItem]:
        items = []
        min_views = filters.get("min_views", 100_000)
        min_likes = filters.get("min_likes", 0)
        max_duration = filters.get("max_duration_seconds", 90)

        meta = self.downloader.prefetch_metadata(url)
        if not meta:
            return items

        if not self.downloader.meets_engagement_threshold(meta, min_views=min_views, min_likes=min_likes):
            logger.debug(f"Skipping {url} — below engagement threshold (views={meta.get('view_count',0)})")
            return items

        if meta.get("duration") and meta["duration"] > max_duration:
            logger.debug(f"Skipping {url} — duration {meta['duration']}s > {max_duration}s")
            return items

        item = ContentItem(
            url=url,
            platform=platform,
            source_type=SourceType.CROSS_PLATFORM,
            niche=niche,
            target_account=AccountProfile.EXCLUSIVE if niche == Niche.EXPLICIT else AccountProfile.MAIN,
            view_count=meta.get("view_count", 0),
            like_count=meta.get("like_count", 0),
            title=meta.get("title"),
            duration_seconds=meta.get("duration"),
            raw_metadata=meta,
        )
        item.compute_engagement_score()
        items.append(item)
        return items

    @staticmethod
    def _load_config() -> dict:
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH) as f:
                return yaml.safe_load(f) or {}
        logger.warning(f"Config not found: {_CONFIG_PATH}. Using empty config.")
        return {}


_PLATFORM_MAP = {
    "youtube":   Platform.YOUTUBE,
    "tiktok":    Platform.TIKTOK,
    "facebook":  Platform.FACEBOOK,
    "snapchat":  Platform.SNAPCHAT,
    "telegram":  Platform.TELEGRAM,
    "instagram": Platform.INSTAGRAM,
}
