import asyncio
import logging
import sys
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any

# Add project root to sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from src.ingestion.downloader import UniversalDownloader

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("EngagementVerify")

def get_reels_via_ytdlp(username: str, limit: int = 20) -> List[str]:
    url = f"https://www.instagram.com/{username}/reels/"
    logger.info(f"💾 Using yt-dlp to find reels for @{username}...")
    
    cmd = [
        "yt-dlp",
        "--print", "url",
        "--playlist-end", str(limit),
        "--flat-playlist",
        "--quiet",
        url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        links = result.stdout.strip().split('\n')
        urls = [link for link in links if "/reel/" in link]
        return urls[:limit]
    except Exception as e:
        logger.error(f"❌ yt-dlp error: {e}")
        return []

async def verify_account_engagement(username: str, limit: int = 20):
    logger.info(f"🚀 Verifying engagement for @{username} (last {limit} reels)...")
    
    reels_urls = get_reels_via_ytdlp(username, limit)
    
    if not reels_urls:
        logger.error("❌ No reels found via yt-dlp.")
        return

    downloader = UniversalDownloader(output_dir=Path("tmp/engagement_verify"))
    results = []
    
    logger.info(f"📊 Found {len(reels_urls)} reels. Fetching metadata...")
    
    for i, reel_url in enumerate(reels_urls):
        sc = reel_url.strip('/').split('/')[-1]
        logger.info(f"🔍 [{i+1}/{len(reels_urls)}] {reel_url}")
        try:
            meta = downloader.prefetch_metadata(reel_url)
            if meta and meta.get("success"):
                info = meta.get("metadata", {})
                likes = info.get("like_count", 0)
                comments = info.get("comment_count", 0)
                views = info.get("view_count", 0)
                results.append({
                    "shortcode": sc,
                    "likes": likes,
                    "comments": comments,
                    "views": views,
                    "engagement": (likes or 0) + (comments or 0)
                })
                logger.info(f"   ❤️ {likes} | 💬 {comments} | 👀 {views}")
            else:
                logger.warning(f"   ⚠️ Could not fetch metadata for {sc}")
        except Exception as e:
            logger.error(f"   ❌ Error: {e}")
            
    # Summary
    if results:
        total_likes = sum(r['likes'] or 0 for r in results)
        avg_likes = total_likes / len(results)
        max_likes = max(r['likes'] or 0 for r in results)
        min_likes = min(r['likes'] or 0 for r in results)
        
        logger.info("========================================")
        logger.info(f"📈 ENGAGEMENT SUMMARY (@{username})")
        logger.info(f"Average Likes: {avg_likes:,.0f}")
        logger.info(f"Max Likes: {max_likes:,.0f}")
        logger.info(f"Min Likes: {min_likes:,.0f}")
        
        # Check against thresholds
        hits_100k_likes = sum(1 for r in results if (r['likes'] or 0) >= 100000)
        hits_10k_combined = sum(1 for r in results if (r['engagement'] or 0) >= 10000)
        
        logger.info(f"🎯 Reels with 100k+ Likes: {hits_100k_likes}")
        logger.info(f"🎯 Reels with 10k+ (Likes + Comments): {hits_10k_combined}")
        logger.info("========================================")
    else:
        logger.error("❌ No data collected.")

if __name__ == "__main__":
    user = sys.argv[1] if len(sys.argv) > 1 else "redbull"
    asyncio.run(verify_account_engagement(user))
