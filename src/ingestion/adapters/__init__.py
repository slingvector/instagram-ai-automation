"""
src/ingestion/adapters/__init__.py
"""
from .dm_adapter import DMAdapter
from .creator_adapter import CreatorAdapter
from .cross_platform_adapter import CrossPlatformAdapter
from .trending_adapter import TrendingAdapter

__all__ = ["DMAdapter", "CreatorAdapter", "CrossPlatformAdapter", "TrendingAdapter"]
