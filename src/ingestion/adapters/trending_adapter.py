"""
src/ingestion/adapters/trending_adapter.py

UC3: Real-Time Trending Monitor (Generic Multi-Source)
Sources (no Twitter/X API required):
  - Reddit JSON API (free, no key)
  - Google Trends via pytrends (no key)
  - YouTube Trending via YouTube Data API v3 (free tier)
  - RSS news feeds via feedparser (BBC, Reuters, AP, Al Jazeera)
  - Telegram public channels via telethon (optional)

Config: config/trending_sources.yaml
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

import yaml

from src.ingestion.base import ContentItem, Niche, Platform, SourceAdapter, SourceType, AccountProfile

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parents[3] / "config" / "trending_sources.yaml"

# Map keywords/topics to niches for smart routing
_NICHE_KEYWORDS = {
    Niche.SPORT:         ["football", "basketball", "soccer", "nba", "nfl", "cricket", "sport"],
    Niche.FASHION:       ["fashion", "style", "outfit", "beauty", "makeup", "clothing"],
    Niche.TRAVEL:        ["travel", "destination", "vacation", "trip", "hotel", "explore"],
    Niche.FUN:           ["funny", "meme", "comedy", "lol", "humor", "viral"],
    Niche.ENTERTAINMENT: ["music", "movie", "celebrity", "actor", "singer", "award"],
}


def _guess_niche(text: str) -> str:
    text_lower = text.lower()
    for niche, keywords in _NICHE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return niche
    return Niche.ENTERTAINMENT  # default


class TrendingAdapter(SourceAdapter):
    """
    Polls multiple trending sources and returns ContentItems each representing
    a trending topic or video URL.
    """

    source_type = SourceType.TRENDING

    def __init__(self):
        self.config = self._load_config()

    def fetch(self) -> List[ContentItem]:
        items: List[ContentItem] = []
        cfg = self.config

        if cfg.get("reddit", {}).get("enabled"):
            items.extend(self._fetch_reddit(cfg["reddit"]))

        if cfg.get("google_trends", {}).get("enabled"):
            items.extend(self._fetch_google_trends(cfg["google_trends"]))

        if cfg.get("youtube", {}).get("enabled"):
            items.extend(self._fetch_youtube_trending(cfg["youtube"]))

        if cfg.get("rss", {}).get("enabled"):
            items.extend(self._fetch_rss(cfg["rss"]))

        if cfg.get("telegram", {}).get("enabled"):
            items.extend(self._fetch_telegram(cfg["telegram"]))

        logger.info(f"TrendingAdapter: fetched {len(items)} items across all sources")
        return items

    # ── Reddit (no API key) ───────────────────────────────────────────────────

    def _fetch_reddit(self, cfg: dict) -> List[ContentItem]:
        import requests
        items = []
        headers = {"User-Agent": "MCR-TrendBot/1.0"}
        min_score = cfg.get("min_score", 1000)
        time_filter = cfg.get("time_filter", "day")

        for subreddit in cfg.get("subreddits", []):
            try:
                url = f"https://www.reddit.com/r/{subreddit}/top.json?t={time_filter}&limit=10"
                resp = requests.get(url, headers=headers, timeout=10)
                data = resp.json()
                for post in data.get("data", {}).get("children", []):
                    d = post["data"]
                    if d.get("score", 0) < min_score:
                        continue
                    # Only take posts with direct video URLs
                    video_url = (d.get("url_overridden_by_dest") or d.get("url") or "")
                    if not any(ext in video_url for ext in [".mp4", ".gif", "v.redd.it", "youtube", "tiktok"]):
                        continue
                    niche = _guess_niche(d.get("title", "") + " " + subreddit)
                    items.append(ContentItem(
                        url=video_url,
                        platform=Platform.REDDIT,
                        source_type=SourceType.TRENDING,
                        niche=niche,
                        view_count=d.get("score", 0),
                        title=d.get("title", ""),
                        raw_metadata=d,
                    ))
            except Exception as e:
                logger.debug(f"Reddit fetch error r/{subreddit}: {e}")

        logger.info(f"Reddit: {len(items)} trending items")
        return items

    # ── Google Trends (pytrends) ──────────────────────────────────────────────

    def _fetch_google_trends(self, cfg: dict) -> List[ContentItem]:
        try:
            from pytrends.request import TrendReq
        except ImportError:
            logger.warning("pytrends not installed. Run: pip install pytrends")
            return []

        items = []
        try:
            geo = cfg.get("geo", "US")
            timeframe = cfg.get("timeframe", "now 1-d")
            pt = TrendReq(hl="en-US", tz=330)
            trending_df = pt.trending_searches(pn="united_states")

            for topic in trending_df[0].tolist()[:10]:
                niche = _guess_niche(topic)
                # Google Trends gives topic keywords, not video URLs
                # We store as a "signal" item — downstream can find matching content
                items.append(ContentItem(
                    url=f"https://www.google.com/search?q={topic.replace(' ', '+')}&tbm=vid",
                    platform=Platform.WEB,
                    source_type=SourceType.TRENDING,
                    niche=niche,
                    title=topic,
                    raw_metadata={"trend_topic": topic, "geo": geo},
                ))
        except Exception as e:
            logger.warning(f"Google Trends fetch error: {e}")

        logger.info(f"Google Trends: {len(items)} topics")
        return items

    # ── YouTube Trending (YouTube Data API v3) ────────────────────────────────

    def _fetch_youtube_trending(self, cfg: dict) -> List[ContentItem]:
        api_key = os.environ.get("YOUTUBE_API_KEY", "")
        if not api_key:
            logger.warning("YOUTUBE_API_KEY not set — skipping YouTube trending")
            return []

        try:
            from googleapiclient.discovery import build
        except ImportError:
            logger.warning("google-api-python-client not installed")
            return []

        items = []
        youtube = build("youtube", "v3", developerKey=api_key)

        for cat_id in cfg.get("category_ids", [23]):
            try:
                resp = youtube.videos().list(
                    part="snippet,statistics,contentDetails",
                    chart="mostPopular",
                    regionCode=cfg.get("region_code", "US"),
                    videoCategoryId=str(cat_id),
                    maxResults=cfg.get("max_results", 10),
                ).execute()

                for video in resp.get("items", []):
                    vid_id  = video["id"]
                    snippet = video["snippet"]
                    stats   = video.get("statistics", {})
                    duration = video.get("contentDetails", {}).get("duration", "")

                    # Only Shorts (≤ 60s) — filter by duration
                    if _parse_yt_duration(duration) > 90:
                        continue

                    niche = _guess_niche(snippet.get("title", "") + " " + snippet.get("description", ""))
                    items.append(ContentItem(
                        url=f"https://www.youtube.com/shorts/{vid_id}",
                        platform=Platform.YOUTUBE,
                        source_type=SourceType.TRENDING,
                        niche=niche,
                        view_count=int(stats.get("viewCount", 0)),
                        like_count=int(stats.get("likeCount", 0)),
                        title=snippet.get("title"),
                        raw_metadata=video,
                    ))
            except Exception as e:
                logger.debug(f"YouTube trending error (cat {cat_id}): {e}")

        logger.info(f"YouTube Trending: {len(items)} Shorts")
        return items

    # ── RSS News Feeds ────────────────────────────────────────────────────────

    def _fetch_rss(self, cfg: dict) -> List[ContentItem]:
        try:
            import feedparser
        except ImportError:
            logger.warning("feedparser not installed. Run: pip install feedparser")
            return []

        items = []
        for feed_cfg in cfg.get("feeds", []):
            try:
                feed = feedparser.parse(feed_cfg["url"])
                for entry in feed.entries[:5]:
                    title    = entry.get("title", "")
                    link     = entry.get("link", "")
                    summary  = entry.get("summary", "")
                    niche    = _guess_niche(title + " " + summary)
                    items.append(ContentItem(
                        url=link,
                        platform=Platform.WEB,
                        source_type=SourceType.TRENDING,
                        niche=niche,
                        title=title,
                        raw_metadata={"source": feed_cfg["name"], "summary": summary},
                    ))
            except Exception as e:
                logger.debug(f"RSS feed error {feed_cfg.get('name')}: {e}")

        logger.info(f"RSS: {len(items)} news items")
        return items

    # ── Telegram public channels ──────────────────────────────────────────────

    def _fetch_telegram(self, cfg: dict) -> List[ContentItem]:
        try:
            from telethon.sync import TelegramClient
        except ImportError:
            logger.warning("telethon not installed. Run: pip install telethon")
            return []

        api_id   = os.environ.get("TELEGRAM_API_ID")
        api_hash = os.environ.get("TELEGRAM_API_HASH")
        if not api_id or not api_hash:
            logger.warning("TELEGRAM_API_ID / TELEGRAM_API_HASH not set — skipping Telegram")
            return []

        items = []
        with TelegramClient("mcr_session", api_id, api_hash) as client:
            for channel in cfg.get("channels", []):
                try:
                    msgs = client.get_messages(channel, limit=20)
                    for msg in msgs:
                        if not msg.video:
                            continue
                        niche = _guess_niche(msg.text or "")
                        items.append(ContentItem(
                            url=f"https://t.me/s/{channel.lstrip('@')}/{msg.id}",
                            platform=Platform.TELEGRAM,
                            source_type=SourceType.TRENDING,
                            niche=niche,
                            title=msg.text[:100] if msg.text else "",
                            raw_metadata={"channel": channel, "message_id": msg.id},
                        ))
                except Exception as e:
                    logger.debug(f"Telegram error {channel}: {e}")

        logger.info(f"Telegram: {len(items)} items")
        return items

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _load_config() -> dict:
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH) as f:
                return yaml.safe_load(f) or {}
        return {}


def _parse_yt_duration(duration: str) -> int:
    """Parse ISO 8601 duration (PT1M30S) to seconds."""
    import re
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
    if not m:
        return 0
    h, mn, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mn * 60 + s
