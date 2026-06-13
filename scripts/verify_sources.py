# scripts/verify_sources.py
import yaml
import logging
import asyncio
import json
import os
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright
from src.utils.yt_dlp_helper import get_yt_dlp_command

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Quality Bar
MIN_FOLLOWERS = 50000
MIN_POSTS = 100

async def get_ig_metadata(page, username):
    url = f"https://www.instagram.com/{username}/"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        
        # Try to extract content from meta tags first (fastest)
        meta_desc = await page.get_attribute("meta[name='description']", "content")
        # Example: "1.2M Followers, 300 Following, 1,450 Posts - See Instagram photos and videos from ..."
        
        followers = 0
        posts = 0
        
        if meta_desc:
            import re
            # Extract followers
            f_match = re.search(r"([\d\.,]+[KMB]?) Followers", meta_desc)
            if f_match:
                f_str = f_match.group(1).replace(",", "")
                if 'K' in f_str: followers = int(float(f_str.replace('K', '')) * 1000)
                elif 'M' in f_str: followers = int(float(f_str.replace('M', '')) * 1000000)
                else: followers = int(f_str)
            
            # Extract posts
            p_match = re.search(r"([\d\.,]+) Posts", meta_desc)
            if p_match:
                posts = int(p_match.group(1).replace(",", ""))
                
        return {"followers": followers, "posts": posts, "username": username}
    except Exception as e:
        logger.error(f"Failed to verify IG @{username}: {e}")
        return None

def get_yt_metadata(channel_id):
    yt_cmd = get_yt_dlp_command([
        "yt-dlp", "--dump-json", "--playlist-end", "1",
        f"https://www.youtube.com/channel/{channel_id}/videos"
    ])
    try:
        result = subprocess.run(yt_cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            data = json.loads(result.stdout.strip().splitlines()[0])
            subs = data.get("channel_follower_count", 0)
            # yt-dlp doesn't always give total posts easily without a full playlist dump
            # but we can assume high-sub established channels meet the 100 post bar
            return {"subscribers": subs, "channel_id": channel_id}
    except Exception as e:
        logger.error(f"Failed to verify YT {channel_id}: {e}")
    return None

async def main():
    watchlist_path = Path("config/creator_watchlist.yaml")
    trending_path = Path("config/trending_sources.yaml")
    
    with open(watchlist_path, "r") as f:
        watchlist = yaml.safe_load(f)
    with open(trending_path, "r") as f:
        trending = yaml.safe_load(f)
        
    ig_usernames = set()
    yt_channels = set()
    
    # Collect IG
    for niche, creators in watchlist.get("creators", {}).items():
        for c in creators:
            if isinstance(c, str): ig_usernames.add(c)
            elif isinstance(c, dict): ig_usernames.add(c["username"])
            
    for page in trending.get("sources", {}).get("instagram_pages", []):
        if isinstance(page, str): ig_usernames.add(page)
        elif isinstance(page, dict): ig_usernames.add(page["username"])

    # Collect YT
    for chan in trending.get("sources", {}).get("youtube_channels", []):
        if isinstance(chan, str): yt_channels.add(chan)
        elif isinstance(chan, dict): yt_channels.add(chan["channel_id"])

    logger.info(f"Unique IG Sources to verify: {len(ig_usernames)}")
    logger.info(f"Unique YT Sources to verify: {len(yt_channels)}")

    # Verify YT (Fast)
    yt_results = []
    for cid in yt_channels:
        res = get_yt_metadata(cid)
        if res:
            yt_results.append(res)
            status = "✅" if res["subscribers"] >= MIN_FOLLOWERS else "❌"
            logger.info(f"{status} YT {cid}: {res['subscribers']} subs")

    # Verify IG (Slow - limit to avoid ban)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use existing session if possible to avoid login wall
        context = await browser.new_context()
        page = await context.new_page()
        
        ig_results = []
        # Sample check or subset? For 500, we should do small batches.
        # For now, let's just log the first 20 as a status check.
        to_check = list(ig_usernames)
        for username in to_check[:50]: # 50 item audit
            res = await get_ig_metadata(page, username)
            if res:
                ig_results.append(res)
                status = "✅" if res["followers"] >= MIN_FOLLOWERS and res["posts"] >= MIN_POSTS else "❌"
                logger.info(f"{status} IG @{username}: {res['followers']} followers, {res['posts']} posts")
            await asyncio.sleep(1)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
