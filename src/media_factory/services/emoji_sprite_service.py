import os
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

class EmojiSpriteService:
    """
    Maps emoji characters to local PNG sprite assets for high-fidelity rendering.
    Supports categorized scanning and hex-code mapping.
    """
    
    # Map semantic vibes to high-fidelity 3D asset hex codes
    SEMANTIC_TAG_MAP = {
        "vibe_heat": ["1f525", "2728", "1f4a5"],        # Fire, Sparkles, Collision
        "vibe_success": ["1f680", "2705", "1f3c6"],    # Rocket, Check, Trophy
        "vibe_money": ["1f4b8", "1f4b0", "1f4b5", "1f4b2"], # Wings, Bag, Dollar, Exchange
        "vibe_growth": ["1f4c8", "1f331", "1f4c4"],    # Chart Up, Seedling, Page
        "vibe_energy": ["26a1", "1f4a1", "2728"],      # Lightning, Bulb, Sparkles
        "vibe_tech": ["2699", "1f4bb", "1f4f1"],        # Gear, Laptop, Phone
        "vibe_love": ["2764", "1f525", "1f60d"],        # Heart, Fire, Heart Eyes
        "vibe_celebration": ["1f389", "1f38a", "2728"], # Party, Confetti, Sparkles
        # New Hero Clusters
        "vibe_nature": ["1f332", "1f33a", "1f33b", "1f30a"], # Pine, Hibiscus, Sunflower, Wave
        "vibe_travel": ["2708", "1f3dd", "1f3d5", "1f6a2"], # Plane, Island, Camping, Ship
        "vibe_fitness": ["1f3cb", "1f4aa", "1f94a", "1f3c3"], # Weight, Muscle, Boxing, Run
        "vibe_food": ["1f354", "1f355", "1f35f", "2615"],     # Burger, Pizza, Fries, Coffee
        "vibe_luxury": ["1f48e", "1f4b0", "1f3ce", "1f512"], # Gem, Money Bag, Racing car, Locked
        "vibe_space": ["1fa90", "1f680", "2728", "1f30c"],   # Planet, Rocket, Sparkles, Galaxy
    }
    
    def __init__(self, 
                 asset_dirs: Optional[list] = None):
        # Default to the newly packed high-quality assets
        if asset_dirs is None:
            asset_dirs = [
                "data/assets/emojis_3d",
                "data/assets/emojis"
            ]
        
        self.asset_dirs = [os.path.abspath(str(d)) for d in asset_dirs]
        self.sprite_map: Dict[str, str] = {} # hex -> absolute_path
        self.keyword_map: Dict[str, List[str]] = {} # keyword -> list[hex]
        self._scan_assets()
        self._load_keyword_db()

    def _load_keyword_db(self):
        """Loads the emoji-to-keyword database for dynamic matching."""
        import json
        db_path = os.path.abspath("src/media_factory/assets/emoji_en_us.json")
        self.keyword_map = {} # keyword -> list[hex]
        
        if os.path.exists(db_path):
            try:
                with open(db_path, "r") as f:
                    data = json.load(f)
                    for char, keywords in data.items():
                        hex_code = self._get_unified_hex(char).lower()
                        if not hex_code:
                            continue
                        for kw in keywords:
                            kw = str(kw).lower()
                            if kw not in self.keyword_map:
                                self.keyword_map[kw] = []
                            if hex_code not in self.keyword_map[kw]:
                                self.keyword_map[kw].append(hex_code)
                logger.info(f"EmojiSpriteService: Loaded {len(self.keyword_map)} keywords for dynamic matching.")
            except Exception as e:
                logger.error(f"Failed to load keyword DB: {e}")

    def _get_unified_hex(self, char: str) -> str:
        """Converts emoji to unified hex format consistent with download script."""
        points = [f"{ord(c):x}" for c in char]
        if len(points) > 1:
            points = [p for p in points if p != 'fe0f'] # Strip invisible modifier
        return "-".join(points)

    def _scan_assets(self):
        """Recursively scans asset directories, utilizing a cache file for instant loads."""
        cache_file = os.path.abspath("data/assets/sprite_map_cache.json")
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        
        # Fast path: Load from cache if it exists
        if os.path.exists(cache_file):
            import json
            try:
                with open(cache_file, "r") as f:
                    self.sprite_map = json.load(f)
                    logger.info(f"EmojiSpriteService: Loaded {len(self.sprite_map)} sprites from fast cache.")
                return
            except Exception as e:
                logger.warning(f"Failed to load sprite cache: {e}. Falling back to disk scan.")

        # Slow path: Scan the disk
        logger.info("EmojiSpriteService: Scanning directories for sprites (Cache Miss)...")
        scan_count = 0
        
        for root_dir in self.asset_dirs:
            if not os.path.exists(root_dir):
                continue
                
            for root, _, files in os.walk(root_dir):
                for file in files:
                    filename = str(file)
                    if filename.endswith(".png"):
                        full_path = os.path.join(str(root), filename)
                        key = os.path.splitext(filename)[0].lower() # hex code
                        
                        # Store by hex code
                        if key not in self.sprite_map:
                            self.sprite_map[key] = full_path
                            scan_count += 1
                            
        logger.info(f"EmojiSpriteService: Indexed {scan_count} unique emoji sprites.")
        
        # Save cache for next time
        try:
            import json
            with open(cache_file, "w") as f:
                json.dump(self.sprite_map, f)
            logger.info(f"EmojiSpriteService: Cached {len(self.sprite_map)} sprites to disk.")
        except Exception as e:
            logger.warning(f"Failed to write sprite cache: {e}")

    def get_sprites_for_pool(self, reaction_pool_str: str, count: int = 5) -> List[str]:
        """
        Parses Gemini's space-separated reaction pool string and returns 
        a list of valid, absolute file paths for the FFmpeg renderer.
        """
        if not reaction_pool_str:
            return []
            
        # Split "vibe_success vibe_money" into ["vibe_success", "vibe_money"]
        tokens = reaction_pool_str.strip().split()
        valid_paths = []
        
        for token in tokens:
            path = self.get_sprite_path(token)
            if path:
                valid_paths.append(path)
                
        if not valid_paths:
            return []

        # If we didn't get enough variety, pad with the first vibe's alternatives
        import random
        while len(valid_paths) < count:
            valid_paths.append(random.choice(valid_paths))
            
        return valid_paths[:count]

    def get_sprite_path(self, query: str) -> Optional[str]:
        """
        Returns the absolute path to the best available PNG sprite.
        Priority: 1. Vibe Tag, 2. Dynamic Keyword, 3. Hex Match, 4. Char Match, 5. Sparkle Fallback.
        """
        import random
        
        # 1. Semantic Vibe Tag Match (Hero Clusters)
        if query in self.SEMANTIC_TAG_MAP:
            hex_choices = self.SEMANTIC_TAG_MAP[query]
            hex_code = random.choice(hex_choices)
            if hex_code in self.sprite_map:
                logger.info(f"EmojiSpriteService: Found 3D asset for Vibe Tag: {query} -> {hex_code}")
                return self.sprite_map[hex_code]
        
        # 2. Open-Domain Dynamic Keyword Match
        if query.startswith("vibe_"):
            keyword = query.replace("vibe_", "").replace("_", " ").lower()
            
            # Try keyword database lookup
            if hasattr(self, 'keyword_map') and keyword in self.keyword_map:
                hex_choices = [h for h in self.keyword_map[keyword] if h in self.sprite_map]
                if hex_choices:
                    hex_code = random.choice(hex_choices)
                    logger.info(f"EmojiSpriteService: Dynamic keyword match (DB) for '{query}' -> {hex_code}")
                    return self.sprite_map[hex_code]
            
            # Fallback to direct filename keyword search
            matches = [path for key, path in self.sprite_map.items() if keyword in path.lower()]
            if matches:
                chosen = random.choice(matches)
                logger.info(f"EmojiSpriteService: Dynamic keyword match (Path) for '{query}' -> {os.path.basename(chosen)}")
                return chosen

        # 3. Direct hex match
        if query.lower() in self.sprite_map:
            return self.sprite_map[query.lower()]
            
        # 4. Unified hex match (from emoji char)
        hex_code = self._get_unified_hex(query).lower()
        if hex_code in self.sprite_map:
            return self.sprite_map[hex_code]
            
        # 5. Production Grade Fallback: Sparkles (2728)
        fallback_hex = "2728"
        if fallback_hex in self.sprite_map:
            if not query.startswith("vibe_") and hex_code != "fe0f":
                logger.warning(f"EmojiSpriteService: No asset for '{query}'. Falling back to Sparkles ({fallback_hex})")
            return self.sprite_map[fallback_hex]

        return None
