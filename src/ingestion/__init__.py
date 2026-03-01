"""src/ingestion/__init__.py"""
from .base import ContentItem, SourceAdapter, Niche, Platform, SourceType, AccountProfile
from .downloader import UniversalDownloader, DownloadResult
from .dedup import ContentDedup

__all__ = [
    "ContentItem", "SourceAdapter", "Niche", "Platform", "SourceType", "AccountProfile",
    "UniversalDownloader", "DownloadResult",
    "ContentDedup",
]
