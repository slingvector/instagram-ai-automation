import subprocess
import yaml
import os
import sys
from typing import List, Set, Optional
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

MANIFEST_PATH = "config/discovery_manifest.yaml"

ADRENALINE_KEYWORDS = [
    "fpv drone racing", "insta360 biking pov", "360 camera tiny planet",
    "downhill mountain bike pov", "motorcycle lane filtering pov",
    "parkour pov", "wingsuit proximity flying", "cliff jumping pov",
    "extreme surfing pov", "motocross helmetcam", "skydiving pov",
    "bmx street pov", "snowboard backcountry pov", "rock climbing pov"
]

ADRENALINE_HASHTAGS = [
    "sendit", "adrenalinejunkie", "helmetcam", "fpvfreestyle", "insta360biking",
    "mtblife", "downhillmtb", "parkourlife", "basejump", "skydiving",
    "bmxfreestyle", "surfinglife", "bigwavesurfing", "snowboarding",
    "backcountry", "climbing", "bouldering", "motocross", "enduro",
    "skateboarding", "extreme", "pov", "goprohero", "insta360"
]

def get_creators_from_platform(platform: str, query: str, max_results: int = 50) -> Set[str]:
    """Uses yt-dlp to find uploader IDs for a given query on a platform."""
    logger.info(f"Searching {platform} for '{query}'...")
    
    # Map platform names for yt-dlp
    search_prefix = {
        "instagram": f"https://www.instagram.com/explore/tags/{query.replace(' ', '')}/" # Fallback to hashtag
    }
    
    if platform == "instagram":
        # yt-dlp doesn't search IG well, so we'll use hashtags or known patterns
        # For now, let's focus on TikTok and then use a fallback for IG
        # Actually, let's try a different approach: searching for 'tiktok' usually works with 'ytsearch:'
        pass

    # Instagram hashtag-based discovery
    cmd = [
        "yt-dlp",
        f"https://www.instagram.com/explore/tags/{query.replace(' ', '')}/",
        "--flat-playlist",
        "--print", "uploader",
        "--playlist-end", str(max_results)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        creators = set(line.strip() for line in result.stdout.splitlines() if line.strip())
        logger.info(f"Found {len(creators)} creators on {platform} for '{query}'.")
        return creators
    except Exception as e:
        logger.error(f"Failed to fetch creators for {platform}/{query}: {e}")
        return set()

def update_manifest(creators: List[dict]):
    with open(MANIFEST_PATH, 'r') as f:
        manifest = yaml.safe_load(f)

    existing_creators = set(c['value'] for c in manifest.get('discovered_creators', []))
    new_count = 0

    for creator in creators:
        if creator['value'] not in existing_creators:
            manifest['discovered_creators'].append(creator)
            existing_creators.add(creator['value'])
            new_count += 1

    with open(MANIFEST_PATH, 'w') as f:
        yaml.dump(manifest, f, sort_keys=False)
    
    logger.info(f"Added {new_count} new creators to {MANIFEST_PATH}.")

def run_hyper_discovery(ig_target: int = 1000, tt_target: int = 500, import_file: Optional[str] = None):
    all_creators = []
    
    if import_file and os.path.exists(import_file):
        logger.info(f"Importing creators from {import_file}...")
        with open(import_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or '|' not in line: continue
                platform, value = line.split('|', 1)
                all_creators.append({
                    "platform": platform.strip().lower(),
                    "type": "creator",
                    "value": value.strip(),
                    "priority": "normal"
                })
        update_manifest(all_creators)
        return

    # TikTok Collection disabled
    pass

    # Instagram Collection
    ig_creators = set()
    for kw in ADRENALINE_KEYWORDS:
        if len(ig_creators) >= ig_target: break
        try:
            cmd = [
                "yt-dlp",
                f"https://www.instagram.com/explore/tags/{kw.replace(' ', '')}/",
                "--flat-playlist",
                "--print", "uploader",
                "--playlist-end", "50"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            new_c = set(line.strip() for line in result.stdout.splitlines() if line.strip())
            ig_creators.update(new_c)
        except: pass

    for c in list(ig_creators)[:ig_target]:
        all_creators.append({"platform": "instagram", "type": "creator", "value": c, "priority": "normal"})

    if all_creators:
        update_manifest(all_creators)
    else:
        logger.warning("No new creators found.")

if __name__ == "__main__":
    ig = 1500
    file_path = None
    if len(sys.argv) > 1:
        if sys.argv[1].endswith(".txt"):
            file_path = sys.argv[1]
        else:
            ig = int(sys.argv[1])
            if len(sys.argv) > 2:
                tt = int(sys.argv[2])
    
    run_hyper_discovery(ig, tt, import_file=file_path)
