# src/utils/proxy_helper.py
import random
import yaml
import logging
import os
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class ProxyHelper:
    def __init__(self, config_path: str = "config/proxy_config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            return {"enabled": False}
        with open(self.config_path, "r") as f:
            try:
                return yaml.safe_load(f) or {"enabled": False}
            except Exception as e:
                logger.error(f"Failed to load proxy config: {e}")
                return {"enabled": False}

    def get_proxy(self, region: str = None) -> Optional[str]:
        if not self.config.get("enabled", False):
            return os.environ.get("PROXY_SERVER")

        region = region or self.config.get("default_region", "global")
        regions = self.config.get("regions", {})
        
        pool = regions.get(region, {}).get("pool", [])
        if not pool and region != "global":
            # Fallback to global pool
            pool = regions.get("global", {}).get("pool", [])
            
        if not pool:
            return os.environ.get("PROXY_SERVER")

        strategy = self.config.get("rotation_strategy", "random")
        if strategy == "random":
            return random.choice(pool)
        else:
            # Simple sequential or first-available? First for now.
            return pool[0]

    def get_playwright_proxy(self, region: str = None) -> Optional[Dict[str, str]]:
        proxy_url = self.get_proxy(region)
        if not proxy_url:
            return None
        return {"server": proxy_url}
