"""
src/ingestion/adapters/trending_adapter.py

UC3: Real-Time Trending Monitor
Fetches viral trends from Reddit, YouTube Trending, and RSS feeds.
Outputs ContentItem instances. 
Implements multi-stage intelligence filtering (Level 2 & Level 3).
Now integrated with Immersive Adrenaline Intelligence.
"""
from __future__ import annotations

import json
import logging
import os
import random
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import yaml
from pathlib import Path
from typing import List, Iterator, Dict, Any, Optional

from src.ingestion.base import ContentItem, Platform, SourceAdapter, SourceType, Niche
from src.ingestion.dedup import ContentDedup, canonical_url
from src.ingestion.downloader import UniversalDownloader
from src.ingestion.services.discovery_service import DiscoveryService
from src.ingestion.services.immersive_classifier import ImmersiveClassifier
from src.utils.yt_dlp_helper import get_yt_dlp_command
from src.utils.proxy_helper import ProxyHelper

logger = logging.getLogger(__name__)

# Fallback open-source/creative-commons or generic IG-friendly B-roll video
GENERIC_BROLL_URL = "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/1080/Big_Buck_Bunny_1080_10s_1MB.mp4"

class TrendingAdapter(SourceAdapter):
    source_type = SourceType.TRENDING

    def __init__(self, manifest_path: str = "config/discovery_manifest.yaml"):
        self.discovery_service = DiscoveryService(manifest_path)
        self.classifier = ImmersiveClassifier()
        self.dedup = ContentDedup()
        
        # Read download strategy from manifest
        tiktok_policy = self.discovery_service.get_downloader_policy(Platform.TIKTOK)
        self.downloader = UniversalDownloader(
            output_dir=Path("data/downloads/tmp"),
            tiktok_policy=tiktok_policy
        )
        
        # Initialize Vertex AI for semantic filtering (Planned for Phase 2)
        try:
            from src.config import GCP_PROJECT_ID
            from src.cloud_function.services.vertex_ai_service import VertexAIService
            self.ai = VertexAIService(project_id=GCP_PROJECT_ID)
        except Exception as e:
            logger.debug(f"Vertex AI not available: {e}")
            self.ai = None
            
        self.proxy_helper = ProxyHelper()
        self.config = self.discovery_service.manifest # For legacy compatibility in some methods

    def fetch(self, exclude_platforms: List[str] = None, min_views: int = None) -> Iterator[ContentItem]:
        if exclude_platforms is None:
            exclude_platforms = []
            
        sources = self.discovery_service.get_sources()
        
        for src in sources:
            platform = src.get("platform")
            if platform in exclude_platforms:
                continue
                
            src_type = src.get("type")
            value = src.get("value")
            
            # Platform-specific and Source-specific override
            filters = src.get("filters", {})
            p_filters = self.discovery_service.get_global_filters(platform)
            
            # Hierarchy: Manual Override > Local YAML Source Filter > Global YAML Platform Filter
            effective_min_views = min_views if min_views else filters.get("min_views", p_filters.get("min_views", 100000))
            effective_max_duration = filters.get("max_duration", p_filters.get("max_duration", 3600))

            niche = src.get("niche")
            
            if platform == Platform.TIKTOK:
                # TikTok support disabled as per high-growth IG focus
                pass
            
            elif platform == Platform.INSTAGRAM:
                # We now route BOTH creators and hashtags to the robust Playwright scraper
                if src_type in ("hashtag", "creator"):
                    target_dict = {src_type: value.strip().lstrip('@')}
                    yield from self._fetch_instagram_pages_bulk([target_dict], effective_min_views, niche=niche)
            
            elif platform == Platform.YOUTUBE:
                if src_type == "keyword":
                    yield from self._fetch_youtube_search(value, effective_min_views, effective_max_duration, niche=niche)
                elif src_type == "creator":
                    yield from self._fetch_youtube_channel({"channel_id": value}, effective_min_views, effective_max_duration, niche=niche)

    def fetch_broad(self, exclude_platforms: List[str] = None, min_views: int = None) -> Iterator[ContentItem]:
        """
        Aggressive Discovery: Fetches raw URLs without deep intelligence filtering.
        Used to quickly populate the SCANNED queue in the state machine.
        """
        if exclude_platforms is None:
            exclude_platforms = []
            
        sources = self.discovery_service.get_sources()
        import random
        random.shuffle(sources)
        for src in sources:
            platform = src.get("platform")
            if platform in exclude_platforms:
                continue
                
            src_type = src.get("type")
            value = src.get("value")
            niche = src.get("niche")
            filters = src.get("filters", {})
            p_filters = self.discovery_service.get_global_filters(platform)
            effective_min_views = min_views if min_views else filters.get("min_views", p_filters.get("min_views", 5000))
            
            logger.info(f"Broad Harvest [{platform}]: {value}...")
            
            if platform == Platform.TIKTOK:
                # TikTok broad mode disabled
                pass
            elif platform == Platform.YOUTUBE:
                if src_type == "keyword":
                    yield from self._fetch_youtube_search(value, effective_min_views, 60, niche=niche, broad_mode=True)
                elif src_type == "creator":
                    yield from self._fetch_youtube_channel({"channel_id": value}, effective_min_views, 60, niche=niche, broad_mode=True)
            elif platform == Platform.INSTAGRAM:
                 # Legacy bridge
                  if src_type == "creator":
                      clean_user = value.strip().lstrip('@')
                      followers = src.get("followers", 0)
                      yield from self._fetch_instagram_pages_bulk(
                          [{"username": clean_user, "follower_baseline": followers}], 
                          effective_min_views, 
                          niche=niche, 
                          broad_mode=True
                      )

    def _fetch_tiktok_creator(self, creator: str, min_views: int, niche: str = None, broad_mode: bool = False) -> Iterator[ContentItem]:
        """Scrape TikTok creator profile."""
        clean_user = creator.strip().lstrip('@')
        logger.info(f"Scanning TikTok creator {'(BROAD)' if broad_mode else '(Immersive Intel)'}: @{clean_user}...")
        effective_niche = niche or Niche.ADRENALINE
        proxy = self.proxy_helper.get_proxy()
        
        # We target the profile directly. TikTok usernames usually start with @ in URL but yt-dlp handles it
        url_target = f"https://www.tiktok.com/@{clean_user}"
        yt_cmd = get_yt_dlp_command([
            "yt-dlp", "--flat-playlist", "--dump-json", 
            "--playlist-end", "50",
            url_target
        ], proxy=proxy)

        try:
            proc = subprocess.run(yt_cmd, capture_output=True, text=True, timeout=90)
            if proc.returncode == 0:
                for line in proc.stdout.strip().splitlines():
                    try:
                        data = json.loads(line)
                        url = data.get("webpage_url")
                        if not url: continue

                        v_count = data.get("view_count", 0)
                        if v_count < min_views: continue
                        
                        if broad_mode:
                            item = ContentItem(
                                url=canonical_url(url), platform=Platform.TIKTOK,
                                source_type=self.source_type, niche=effective_niche,
                                view_count=v_count, title=data.get("title", "No Title")
                            )
                            yield item
                            continue

                        # Intel and dedup
                        # ... Similar to keyword logic but for creator ...
                        meta = self.downloader.prefetch_metadata(url)
                        if not meta: continue
                        
                        v_score = self.discovery_service.compute_virality_score(meta)
                        item = ContentItem(
                            url=canonical_url(url), platform=Platform.TIKTOK,
                            source_type=self.source_type, niche=effective_niche,
                            engagement_score=v_score, view_count=meta["view_count"],
                            title=meta.get("title", ""),
                            raw_metadata={"creator": clean_user}
                        )
                        if not self.dedup.is_duplicate(item):
                            self.dedup.register(item)
                            yield item
                            logger.info(f"🔥 Immersive Creator Discovery [Score: {v_score}]: {url}")
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"TikTok creator fetch failed: {e}")
        """Scrape TikTok for keywords. If broad_mode, skip deep metric filtering."""
        logger.info(f"Scanning TikTok {'(BROAD)' if broad_mode else '(Immersive Intel)'} for: '{keyword}'...")
        effective_niche = niche or Niche.ADRENALINE
        proxy = self.proxy_helper.get_proxy()
        yt_cmd = get_yt_dlp_command([
            "yt-dlp", "--flat-playlist", "--dump-json", 
            f"https://www.tiktok.com/search?q={keyword}"
        ], proxy=proxy)
        
        p_filters = self.discovery_service.get_global_filters(Platform.TIKTOK)
        min_like_rate = p_filters.get("min_like_rate", 0.0)
        min_comment_rate = p_filters.get("min_comment_rate", 0.0)

        try:
            proc = subprocess.run(yt_cmd, capture_output=True, text=True, timeout=90)
            if proc.returncode == 0:
                for line in proc.stdout.strip().splitlines():
                    try:
                        data = json.loads(line)
                        url = data.get("webpage_url")
                        if not url: continue

                        # Stage 1: Basic View Prefilter (Fast)
                        v_count = data.get("view_count", 0)
                        if v_count < min_views:
                            continue
                        
                        if broad_mode:
                            # Direct yield for aggressive population
                            item = ContentItem(
                                url=canonical_url(url),
                                platform=Platform.TIKTOK,
                                source_type=self.source_type,
                                niche=effective_niche,
                                view_count=v_count,
                                title=data.get("title", "No Title")
                            )
                            yield item
                            continue

                        # Stage 2: Engagement Intelligence (Deep Signal)
                        meta = self.downloader.prefetch_metadata(url)
                        if not meta: continue

                        rates = self.discovery_service.calculate_rates(
                            meta["view_count"], meta["like_count"], meta["comment_count"]
                        )
                        
                        if rates["like_rate"] < min_like_rate or rates["comment_rate"] < min_comment_rate:
                            continue

                        # Stage 3: Immersive Classification (Pivot Logic)
                        immersive_meta = self.classifier.classify(meta.get("title", ""), keyword)
                        
                        # Stage 4: Virality Momentum (Ranking)
                        v_score = self.discovery_service.compute_virality_score({
                            "view_count": meta["view_count"],
                            "like_count": meta["like_count"],
                            "comment_count": meta["comment_count"],
                            "upload_timestamp": meta["upload_timestamp"]
                        })

                        item = ContentItem(
                            url=canonical_url(url),
                            platform=Platform.TIKTOK,
                            source_type=self.source_type,
                            niche=effective_niche,
                            engagement_score=v_score,
                            view_count=meta["view_count"],
                            like_count=meta["like_count"],
                            comment_count=meta["comment_count"],
                            upload_timestamp=meta["upload_timestamp"],
                            title=meta.get("title", ""),
                            immersive_metadata=immersive_meta,
                            raw_metadata={
                                "creator": data.get("uploader"), 
                                "keyword": keyword,
                                "rates": rates,
                                "hook": self.discovery_service.get_hook_config(keyword)
                            }
                        )
                        
                        if not self.dedup.is_duplicate(item):
                            self.discovery_service.record_discovery(Platform.TIKTOK, "keyword", keyword, item.raw_metadata)
                            self.dedup.register(item)
                            yield item
                            logger.info(f"🔥 Immersive Discovery [Score: {v_score}, Cat: {immersive_meta['type']}]: {url}")
                        else:
                            logger.debug(f"Skipping duplicate TikTok item: {item.url}")
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"TikTok keyword fetch failed: {e}")

    def _fetch_youtube_search(self, term: str, min_views: int = None, max_duration: int = 3600, niche: str = None, broad_mode: bool = False) -> Iterator[ContentItem]:
        """Scrape YouTube for SEO terms. If broad_mode, skip deep metric filtering."""
        logger.info(f"Scanning YouTube {'(BROAD)' if broad_mode else '(Immersive Intel)'} for: '{term}'...")
        effective_niche = niche or Niche.ADRENALINE
        proxy = self.proxy_helper.get_proxy()
        yt_cmd = get_yt_dlp_command([
            "yt-dlp", "--flat-playlist", "--dump-json", f"ytsearch200:{term}"
        ], proxy=proxy)
        
        p_filters = self.discovery_service.get_global_filters(Platform.YOUTUBE)
        min_like_rate = p_filters.get("min_like_rate", 0.0)
        min_comment_rate = p_filters.get("min_comment_rate", 0.0)

        try:
            proc = subprocess.run(yt_cmd, capture_output=True, text=True, timeout=120)
            if proc.returncode == 0:
                for line in proc.stdout.strip().splitlines():
                    try:
                        data = json.loads(line)
                        vid_id = data.get("id")
                        if not vid_id: continue
                        url = f"https://www.youtube.com/watch?v={vid_id}"

                        duration = data.get("duration", 0)
                        if duration and duration > max_duration:
                            continue
                        
                        v_count = data.get("view_count", 0)
                        if min_views and v_count < min_views:
                            continue

                        if broad_mode:
                            item = ContentItem(
                                url=canonical_url(url),
                                platform=Platform.YOUTUBE,
                                source_type=self.source_type,
                                niche=effective_niche,
                                view_count=v_count,
                                title=data.get("title", "No Title")
                            )
                            yield item
                            continue

                        meta = self.downloader.prefetch_metadata(url)
                        if not meta: continue

                        rates = self.discovery_service.calculate_rates(
                            meta["view_count"], meta["like_count"], meta["comment_count"]
                        )
                        
                        if rates["like_rate"] < min_like_rate or rates["comment_rate"] < min_comment_rate:
                            continue

                        # Immersive Classification
                        immersive_meta = self.classifier.classify(meta.get("title", ""), term)

                        v_score = self.discovery_service.compute_virality_score({
                            "view_count": meta["view_count"],
                            "like_count": meta["like_count"],
                            "comment_count": meta["comment_count"],
                            "upload_timestamp": meta["upload_timestamp"]
                        })

                        item = ContentItem(
                            url=canonical_url(url),
                            platform=Platform.YOUTUBE,
                            source_type=self.source_type,
                            niche=effective_niche,
                            engagement_score=v_score,
                            view_count=meta["view_count"],
                            like_count=meta["like_count"],
                            comment_count=meta["comment_count"],
                            upload_timestamp=meta["upload_timestamp"],
                            title=meta.get("title", ""),
                            immersive_metadata=immersive_meta,
                            raw_metadata={
                                "creator": data.get("uploader"), 
                                "keyword": term,
                                "rates": rates,
                                "hook": self.discovery_service.get_hook_config(term)
                            }
                        )

                        if not self.dedup.is_duplicate(item):
                            message_id = f"yt_seo::{vid_id}"
                            if not self.dedup.is_dm_seen(message_id):
                                self.discovery_service.record_discovery(Platform.YOUTUBE, "keyword", term, item.raw_metadata)
                                self.dedup.register(item)
                                self.dedup.register_dm(message_id, url, url)
                                yield item
                                logger.info(f"🔥 Immersive Discovery [Score: {v_score}, Cat: {immersive_meta['type']}]: {url}")
                        else:
                            logger.debug(f"Skipping duplicate YouTube item: {item.url}")
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"YouTube search fetch failed: {e}")

    def _fetch_youtube_channel(self, chan_info: str | dict, min_views: int = None, max_duration: int = 3600, niche: str = None, broad_mode: bool = False) -> Iterator[ContentItem]:
        """Fetch videos from a YouTube channel and apply virality intelligence."""
        effective_niche = niche or Niche.ADRENALINE
        if isinstance(chan_info, str):
            chan_id = chan_info
            chan_name = chan_id
        else:
            chan_id = chan_info.get("channel_id")
            chan_name = chan_info.get("name", chan_id)

        logger.info(f"Scanning YouTube channel (Immersive Intel): {chan_name}...")
        proxy = self.proxy_helper.get_proxy()
        yt_cmd = get_yt_dlp_command([
            "yt-dlp", "--flat-playlist", "--dump-json", 
            "--playlist-end", "50",
            f"https://www.youtube.com/channel/{chan_id}/videos"
        ], proxy=proxy)
        
        try:
            proc = subprocess.run(yt_cmd, capture_output=True, text=True, timeout=60)
            if proc.returncode == 0:
                for line in proc.stdout.strip().splitlines():
                    try:
                        data = json.loads(line)
                        vid_id = data.get("id")
                        url = f"https://www.youtube.com/watch?v={vid_id}"
                        
                        v_count = data.get("view_count", 0)
                        if min_views and v_count < min_views:
                            continue

                        if broad_mode:
                            item = ContentItem(
                                url=canonical_url(url),
                                platform=Platform.YOUTUBE,
                                source_type=self.source_type,
                                niche=effective_niche,
                                view_count=v_count,
                                title=data.get("title", "No Title")
                            )
                            yield item
                            continue

                        meta = self.downloader.prefetch_metadata(url)
                        if not meta: continue

                        immersive_meta = self.classifier.classify(meta.get("title", ""), chan_name)

                        v_score = self.discovery_service.compute_virality_score({
                            "view_count": meta["view_count"],
                            "like_count": meta["like_count"],
                            "comment_count": meta["comment_count"],
                            "upload_timestamp": meta["upload_timestamp"]
                        })

                        message_id = f"yt_chan::{vid_id}"
                        if not self.dedup.is_dm_seen(message_id):
                            item = ContentItem(
                                url=canonical_url(url),
                                platform=Platform.YOUTUBE,
                                source_type=self.source_type,
                                niche=effective_niche, 
                                engagement_score=v_score,
                                view_count=meta["view_count"],
                                title=meta.get("title", ""),
                                duration_seconds=meta.get("duration"),
                                immersive_metadata=immersive_meta,
                                raw_metadata={"text_prompt": meta.get("title", ""), "channel": chan_name}
                            )
                            if not self.dedup.is_duplicate(item):
                                self.dedup.register(item)
                                self.dedup.register_dm(message_id, url, url)
                                yield item
                                logger.info(f"🔥 Immersive Discovery [Score: {v_score}, Cat: {immersive_meta['type']}]: {url}")
                            else:
                                logger.debug(f"Skipping duplicate YouTube channel item: {item.url}")
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"YouTube channel fetch failed: {e}")

    def _fetch_reddit(self, subreddit: str, min_views: int = None, niche: str = None) -> Iterator[ContentItem]:
        """Reddit fetcher updated with immersive intel scoring."""
        logger.info(f"Scanning Reddit r/{subreddit} (Immersive Intel)...")
        effective_niche = niche or Niche.ADRENALINE
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=100"
        data_bytes = self._safe_get(url)
        if not data_bytes: return
            
        try:
            data = json.loads(data_bytes.decode('utf-8'))
            children = data.get('data', {}).get('children', [])
            
            valid_posts = []
            for child in children:
                post = child.get('data', {})
                # Reddit floor usually 1/20th of views
                score = post.get('ups', 0)
                reddit_floor = min_views // 20 if min_views else 5000
                if score < reddit_floor:
                    continue
                valid_posts.append(post)
                
            if not valid_posts: return
                
            # Sort and Score
            for post in valid_posts:
                title = post.get('title', '')
                ups = post.get('ups', 0)
                num_comments = post.get('num_comments', 0)
                post_url = "https://www.reddit.com" + post.get('permalink', '')
                is_video = post.get('is_video', False)
                target_url = post_url if is_video else GENERIC_BROLL_URL
                
                # Immersive Classification
                immersive_meta = self.classifier.classify(title, subreddit)

                # Mock intel signals for Reddit (ups as views/likes proxy)
                v_score = self.discovery_service.compute_virality_score({
                    "view_count": ups * 20,
                    "like_count": ups,
                    "comment_count": num_comments,
                    "upload_timestamp": int(post.get('created_utc', 0))
                })

                item = ContentItem(
                    url=canonical_url(target_url),
                    platform=Platform.REDDIT,
                    source_type=self.source_type,
                    niche=effective_niche,
                    engagement_score=v_score,
                    view_count=ups * 20,
                    like_count=ups,
                    comment_count=num_comments,
                    title=title,
                    immersive_metadata=immersive_meta,
                    raw_metadata={"reddit_post_url": post_url}
                )
                
                message_id = f"reddit::{post.get('id')}"
                if not self.dedup.is_dm_seen(message_id):
                    if not self.dedup.is_duplicate(item):
                        self.dedup.register(item)
                        self.dedup.register_dm(message_id, post_url, target_url)
                        yield item
                        logger.info(f"🔥 Reddit Discovery [Score: {v_score}, Cat: {immersive_meta['type']}]: {title}")
                    else:
                        logger.debug(f"Skipping duplicate Reddit item: {item.url}")
                    
        except Exception as e:
            logger.error(f"Reddit fetch failed: {e}")

    def _safe_get(self, url: str, headers: dict = None, region: str = None) -> bytes:
        if headers is None:
            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) IGAutomation/1.0'}
        proxy_url = self.proxy_helper.get_proxy(region)
        if proxy_url:
            proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
            opener = urllib.request.build_opener(proxy_handler)
        else:
            opener = urllib.request.build_opener()
        req = urllib.request.Request(url, headers=headers)
        try:
            with opener.open(req, timeout=15) as response:
                return response.read()
        except Exception:
            return b""

    def _fetch_instagram_hashtag(self, hashtag: str, min_likes: int, niche: str = None) -> Iterator[ContentItem]:
        # ... logic ...
        effective_niche = niche or Niche.ADRENALINE
        # (The rest of the method will now use this effective_niche)
        return iter([])

    def _fetch_instagram_pages_bulk(self, pages: List[dict], min_views: int = None, niche: str = None, broad_mode: bool = False) -> Iterator[ContentItem]:
        # Legacy CreatorAdapter bridge
        effective_niche = niche or Niche.ADRENALINE
        from src.ingestion.adapters.creator_adapter import CreatorAdapter
        import tempfile
        import yaml # ensure yaml is imported in this scope
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
            # Use the provided niche in the mock config for CreatorAdapter
            niche_str = effective_niche.value if hasattr(effective_niche, 'value') else str(effective_niche)
            mock_config = {
                "filters": {"min_views": min_views or 100000}, 
                "creators": {niche_str: pages}
            }
            yaml.dump(mock_config, tmp)
            tmp_path = tmp.name
        try:
            adapter = CreatorAdapter(config_paths=[tmp_path])
            for item in adapter.fetch(min_views=min_views, broad_mode=broad_mode):
                item.source_type = self.source_type
                yield item
        finally:
            if os.path.exists(tmp_path): os.remove(tmp_path)

    def _fetch_rss(self, feed_url: str) -> Iterator[ContentItem]:
        # Minimal RSS fetcher (News topics)
        xml_bytes = self._safe_get(feed_url)
        if not xml_bytes: return
        try:
            root = ET.fromstring(xml_bytes)
            for item_elem in root.findall(".//item"):
                title = item_elem.findtext("title")
                link = item_elem.findtext("link")
                if title and link:
                    item = ContentItem(url=GENERIC_BROLL_URL, platform=Platform.WEB, source_type=self.source_type, title=title)
                    yield item
        except Exception:
            pass
