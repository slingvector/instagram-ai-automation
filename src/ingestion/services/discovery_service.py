"""
src/ingestion/services/discovery_service.py

Handles YAML-driven content acquisition and auto-expansion of sources.
Implements 'Self-Evolving YAML' logic: seed -> discover creators -> update YAML.
"""
import logging
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class DiscoveryService:
    def __init__(self, manifest_path: str = "config/discovery_manifest.yaml"):
        self.manifest_path = Path(manifest_path)
        self.manifest = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            return {"sources": [], "discovered_creators": [], "global_filters": {}}
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def save(self):
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(self.manifest, f, sort_keys=False)

    def get_sources(self, platform: Optional[str] = None) -> List[Dict[str, Any]]:
        sources = self.manifest.get("sources", [])
        discovered = self.manifest.get("discovered_creators", [])
        all_sources = sources + discovered
        if platform:
            return [s for s in all_sources if s.get("platform") == platform]
        return all_sources

    def get_global_filters(self, platform: str) -> Dict[str, Any]:
        return self.manifest.get("global_filters", {}).get(platform, {})

    def get_downloader_policy(self, platform: str) -> str:
        """Get the download strategy (e.g. snaptik, ytdlp) for a platform."""
        return self.get_global_filters(platform).get("downloader_policy", "ytdlp")

    def record_discovery(self, platform: str, source_type: str, value: str, metadata: Dict[str, Any]):
        """
        Record a high-performing discovery and potentially expand the manifest.
        Rules:
        - If we find a viral video, add its creator to 'discovered_creators' if not already there.
        """
        discovered = self.manifest.setdefault("discovered_creators", [])
        
        creator = metadata.get("creator") or metadata.get("author")
        if not creator:
            return

        # Simple dedup for discovered creators
        existing = {str(c.get("value")).lower() for c in discovered if isinstance(c, dict)}
        if creator.lower() not in existing:
            new_entry = {
                "platform": platform,
                "type": "creator",
                "value": creator,
                "discovery_origin": value,
                "priority": "normal"
            }
            discovered.append(new_entry)
            logger.info(f"✨ Auto-Expanding Manifest: Discovered new Elite Creator @{creator} on {platform}")
            self.save()

    def get_hook_config(self, source_value: str) -> Dict[str, Any]:
        """Get hook instructions for a specific seed/source."""
        for s in self.manifest.get("sources", []):
            if s.get("value") == source_value:
                return s.get("hook", {"enabled": True, "strategy": "llm_v1"})
        return {"enabled": True, "strategy": "llm_v1"}

    # --- Intelligence Signal Helpers ---

    @staticmethod
    def calculate_rates(views: int, likes: int, comments: int) -> Dict[str, float]:
        """Calculate engagement quality ratios."""
        if views <= 0:
            return {"like_rate": 0.0, "comment_rate": 0.0}
        return {
            "like_rate": float(round(likes / views, 4)),
            "comment_rate": float(round(comments / views, 4))
        }

    @staticmethod
    def calculate_velocity(views: int, timestamp: Optional[int]) -> float:
        """Calculate Growth Velocity (Views per Hour)."""
        import time
        if timestamp is None or views <= 0:
            return 0.0
        
        hours_since = (time.time() - float(timestamp)) / 3600
        # Floor hours to 1 to avoid division by zero or inflated scores for brand new videos
        effective_hours = max(1.0, float(hours_since))
        return float(round(views / effective_hours, 2))

    def compute_virality_score(self, item_data: Dict[str, Any]) -> float:
        """
        Phase 1 Scoring Engine:
        Combines Growth Velocity and Engagement Quality.
        """
        views = item_data.get("view_count", 0)
        likes = item_data.get("like_count", 0)
        comments = item_data.get("comment_count", 0)
        timestamp = item_data.get("upload_timestamp")

        rates = self.calculate_rates(views, likes, comments)
        velocity = self.calculate_velocity(views, timestamp)

        # Normalization (Log-based to handle massive outliers)
        import math
        # 10k views/hr is a strong 1.0 baseline for velocity
        velocity_score = math.log10(max(1, velocity)) / 4.0  
        
        # Like rate caps at 10% (0.1)
        like_score = min(1.0, rates["like_rate"] / 0.1)
        
        # Comment rate caps at 2% (0.02)
        comment_score = min(1.0, rates["comment_rate"] / 0.02)

        # Phase 1 Weights
        final_score = (
            velocity_score * 0.5 +
            like_score * 0.3 +
            comment_score * 0.2
        )
        return float(round(final_score, 4))
