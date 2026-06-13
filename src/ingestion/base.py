"""
src/ingestion/base.py

Shared types for the ingestion layer.
Every Source Adapter produces List[ContentItem] which feeds the downstream
processing pipeline (download → Media Factory → GCS → Firestore → Appium).
"""
from __future__ import annotations

import math
import yaml
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse, urlunparse


# ── Account profiles ──────────────────────────────────────────────────────────

class AccountProfile(str, Enum):
    """Logical posting account identifiers."""
    MAIN      = "main"         # General niches: fashion, travel, entertainment, sport, fun
    EXCLUSIVE = "exclusive"    # Explicit-content — private, fully isolated account


# ── Niche taxonomy ────────────────────────────────────────────────────────────

class Niche(str, Enum):
    FASHION       = "fashion"
    TRAVEL        = "travel"
    ENTERTAINMENT = "entertainment"
    SPORT         = "sport"
    FUN           = "fun"
    NEWS          = "news"
    TECH          = "tech"
    FINANCE       = "finance"
    NATURE        = "nature"
    ADRENALINE    = "adrenaline"
    EXPLICIT      = "explicit"   # → always routed to AccountProfile.EXCLUSIVE


# ── Platform identifiers ──────────────────────────────────────────────────────

class Platform(str, Enum):
    INSTAGRAM = "instagram"
    TIKTOK    = "tiktok"
    YOUTUBE   = "youtube"
    TELEGRAM  = "telegram"
    FACEBOOK  = "facebook"
    SNAPCHAT  = "snapchat"
    REDDIT    = "reddit"
    TWITTER   = "twitter"
    WEB       = "web"           # Generic web source (news, trending)


# ── Source types ──────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    DM             = "dm"             # UC1: Instagram DMs
    CREATOR        = "creator"        # UC2: Creator watchlist
    TRENDING       = "trending"       # UC3: Real-time trend monitor
    CROSS_PLATFORM = "cross_platform" # UC4: TikTok, YT Shorts, etc.


# ── Cached config loading ────────────────────────────────────────────────────

_CONFIG_CACHE: dict | None = None
_CONFIG_PATH = Path("config/uvi_config.yaml")


def _load_uvi_config() -> dict:
    """Load UVI config from disk, cached after first call."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, "r") as f:
                _CONFIG_CACHE = yaml.safe_load(f) or {}
        except Exception:
            _CONFIG_CACHE = {}
    else:
        _CONFIG_CACHE = {}
    return _CONFIG_CACHE


# ── Core data model ───────────────────────────────────────────────────────────

@dataclass
class ContentItem:
    """
    A single piece of content ready to enter the processing pipeline.
    Produced by source adapters; consumed by UniversalDownloader and upstream
    pipeline stages (Media Factory → GCS → Firestore job).
    """
    # Required
    url:            str
    platform:       str   # Platform.*
    source_type:    str   # SourceType.*
    niche:          str   # Niche.*

    # Routing
    target_account: str = AccountProfile.MAIN  # Override to EXCLUSIVE for explicit

    # Engagement signals (0.0 if unknown)
    engagement_score: float = 0.0
    view_count:       int   = 0
    like_count:       int   = 0
    comment_count:    int   = 0
    save_count:       int   = 0
    share_count:      int   = 0
    upload_timestamp: Optional[int] = None

    # Audio
    audio_url:    Optional[str] = None   # Original audio URL (for mood matching)
    audio_title:  Optional[str] = None   # Track name if known
    keep_audio:   bool = True            # False → replace with IG trending audio

    # Content metadata
    creator_username: Optional[str] = None
    title:            Optional[str] = None
    duration_seconds: Optional[int] = None
    shortcode:        Optional[str] = None  # IG reel shortcode for dedup

    # Immersive Intelligence (Phase 1: Meta-tags)
    immersive_metadata: dict = field(default_factory=dict) # {type, motion, perspective, score}

    # Extra provider-specific data
    raw_metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        # Explicit content always goes to the exclusive account
        if self.niche == Niche.EXPLICIT:
            self.target_account = AccountProfile.EXCLUSIVE

    @property
    def dedup_key(self) -> str:
        """Canonical dedup key. Uses shortcode for IG, else normalized URL."""
        if self.shortcode:
            return f"{self.platform}::{self.shortcode}"
        # Strip tracking params from URL
        p = urlparse(self.url)
        return urlunparse((p.scheme, p.netloc, p.path, '', '', ''))

    def compute_engagement_score(self) -> float:
        """
        Weighted engagement score for content ranking/filtering.
        Loads weights from cached yaml config.
        """
        cfg = _load_uvi_config()
        weights = {"view": 0.1, "like": 1.0, "save": 5.0, "share": 3.0}  # Fallbacks
        weights.update(cfg.get("engagement_weights", {}))

        score = (
            self.view_count  * weights["view"]  +
            self.like_count  * weights["like"]  +
            self.save_count  * weights["save"]  +
            self.share_count * weights["share"]
        )
        self.engagement_score = score
        return score


# ── Source Adapter ABC ────────────────────────────────────────────────────────

class SourceAdapter(ABC):
    """
    Base class for all content ingestion adapters.
    Each adapter implements fetch() and returns normalized ContentItems.
    """

    source_type: str = ""   # Must be overridden by subclass

    @abstractmethod
    def fetch(self) -> List[ContentItem]:
        """
        Fetch new content from the source.
        Returns only items that have not already been processed (dedup is caller's responsibility).
        """
        ...

    def get_platform_config(self, platform: str) -> dict:
        """
        Load platform-specific filters and enablement from uvi_config.yaml (cached).
        """
        cfg = _load_uvi_config()

        # Default fallbacks
        p_cfg = {
            "enabled": True,
            "min_views": 100000,
            "multiplier": 1.0,
            "baseline": 0.0
        }
        p_cfg.update(cfg.get("platforms", {}).get(platform, {}))
        return p_cfg

    def calculate_uvi(self, platform: str, raw_metric: float) -> float:
        """
        Universal Virality Index (UVI) Calculation.
        Formula: log10(RawMetric * Multiplier) - Baseline
        """
        p_cfg = self.get_platform_config(platform)
        
        if raw_metric <= 0:
            return 0.0
            
        score = math.log10(raw_metric * p_cfg["multiplier"]) - p_cfg["baseline"]
        return max(0.0, score)

    def run(self) -> List[ContentItem]:
        """
        Called by the scheduler. Fetches, deduplicates, and returns items
        ready for downstream processing.
        """
        from src.ingestion.dedup import ContentDedup
        items = self.fetch()
        dedup = ContentDedup()
        new_items = [item for item in items if not dedup.is_duplicate(item)]
        for item in new_items:
            dedup.register(item)
        return new_items

