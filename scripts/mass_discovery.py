import os
import re
import json
import yaml
import asyncio
import logging
import random
import re
import yaml
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Any, Optional
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from src.ingestion.base import ContentItem, Platform, SourceType
from src.ingestion.downloader import UniversalDownloader
from src.utils.google_drive_service import GoogleDriveService

# Add project root to sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

# User Agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MassDiscoveryEngine:
    def __init__(self, seed_files: List[str], target_accounts: int = 10000, target_reels: int = 500):
        self.seed_files = [Path(f) for f in seed_files]
        self.target_accounts = target_accounts
        self.target_reels = target_reels
        self.discovered_accounts: Set[str] = set()
        self.elite_accounts: Dict[str, int] = {} # username -> followers
        self.viral_reels: List[Dict[str, Any]] = []
        self.processed_accounts: Set[str] = set()
        
        self.downloader = UniversalDownloader(output_dir=Path("data/downloads/mass_scale"))
        self.drive_service = GoogleDriveService()
        
        # Load seeds
        self._load_seeds()

    def _load_seeds(self):
        for seed_file in self.seed_files:
            if not seed_file.exists():
                logger.warning(f"Seed file {seed_file} not found.")
                continue
            with open(seed_file, "r") as f:
                for line in f:
                    if "|" in line:
                        parts = line.strip().split("|")
                        if len(parts) >= 2 and parts[0] == "instagram":
                            self.discovered_accounts.add(parts[1])
                    else:
                        cleaned = line.strip().lstrip('@')
                        if cleaned:
                            self.discovered_accounts.add(cleaned)
        logger.info(f"Loaded {len(self.discovered_accounts)} seed accounts.")

    async def _google_search_discovery(self):
        """Use web search to find more elite creators."""
        queries = [
            "top instagram adrenaline creators 1M followers",
            "most popular extreme sports instagram accounts 2024",
            "top travel influencers instagram over 1 million followers",
            "best FPV drone pilots instagram top accounts"
        ]
        
        from src.utils.search_web import search_web # Local import to avoid circular dependencies if any
        for query in queries:
            logger.info(f"Searching Google for: {query}")
            try:
                # This is a mock/simulated call to a tool-like function if available in the codebase
                # Since I am the agent, I'll use my knowledge or tools later if needed.
                # For now, I'll add a placeholder that can be extended.
                pass 
            except Exception as e:
                logger.error(f"Google search failed: {e}")

    async def _human_sleep(self, min_val: float = 1.0, max_val: float = 3.0):
        await asyncio.sleep(random.uniform(min_val, max_val))

    async def _get_follower_count(self, page) -> int:
        """Extract follower count from profile."""
        try:
            content = await page.evaluate("""() => {
                let meta = document.querySelector('meta[name="description"]');
                return meta ? meta.content : "";
            }""")
            if content:
                m = re.search(r'([\d\.,]+[kKmM]?)\s+Followers', content, re.IGNORECASE)
                if m:
                    val_str = m.group(1).upper().replace(',', '')
                    if 'M' in val_str:
                        return int(float(val_str.replace('M', '')) * 1000000)
                    elif 'K' in val_str:
                        return int(float(val_str.replace('K', '')) * 1000)
                    else:
                        return int(val_str)
        except Exception as e:
            logger.debug(f"Follower count extraction failed: {e}")
        return 0

    async def _extract_suggested_accounts(self, page) -> Set[str]:
        """Extract suggested accounts from a profile page."""
        suggested = set()
        try:
            links = await page.query_selector_all('a[href^="/"]')
            for link in links:
                href = await link.get_attribute("href")
                if href and href.strip('/') and '/' not in href.strip('/'):
                    username = href.strip('/')
                    if username not in ['explore', 'reels', 'direct', 'accounts', 'emails', 'about', 'help', 'press', 'api', 'privacy', 'terms', 'locations']:
                        suggested.add(username)
        except Exception as e:
            logger.warning(f"Suggested accounts extraction failed: {e}")
        return suggested

    def _parse_metric(self, text: str) -> int:
        """Parse strings like '1.4M', '615K' into integers."""
        if not text: return 0
        text = text.upper().replace(',', '').strip()
        match = re.search(r'([\d.]+)([KM]?)', text)
        if not match: return 0
        
        val, unit = match.groups()
        val = float(val)
        if unit == 'M': val *= 1000000
        elif unit == 'K': val *= 1000
        return int(val)

    async def _scrape_reels_from_grid(self, page) -> List[Dict[str, Any]]:
        """Extract reels and view counts directly from the grid DOM."""
        reels = []
        try:
            # More specific selector for reels
            elements = await page.query_selector_all('a[href*="/reel/"]')
            for el in elements:
                href = await el.get_attribute("href")
                if not href: continue
                
                parts = href.strip('/').split('/')
                # Href usually is /username/reel/SHORTCODE/
                if 'reel' in parts:
                    idx = parts.index('reel')
                    if idx + 1 < len(parts):
                        shortcode = parts[idx + 1]
                    else:
                        continue
                else:
                    continue
                
                # Get all text from the anchor
                # View count text like "1M" is usually in a nested span
                all_text = await el.inner_text()
                aria_label = await el.get_attribute("aria-label") or ""
                
                # Combine for search
                combined = f"{all_text} {aria_label}"
                views = self._parse_metric(combined)
                
                if shortcode and views > 0:
                    reels.append({
                        "shortcode": shortcode,
                        "views": views
                    })
            
            # De-duplicate by shortcode
            seen = set()
            unique_reels = []
            for r in reels:
                if r["shortcode"] not in seen:
                    unique_reels.append(r)
                    seen.add(r["shortcode"])
            return unique_reels
            
        except Exception as e:
            logger.debug(f"Grid extraction failed: {e}")
        return reels

    async def _fetch_deep_metrics(self, shortcode: str, username: str) -> Optional[Dict[str, Any]]:
        """Use yt-dlp to fetch likes and comments for a specific reel."""
        url = f"https://www.instagram.com/reel/{shortcode}/"
        try:
            # This uses the UniversalDownloader which handles yt-dlp prefetch
            meta = self.downloader.prefetch_metadata(url)
            if meta and meta.get("success"):
                info = meta.get("metadata", {})
                return {
                    "shortcode": shortcode,
                    "views": info.get("view_count", 0),
                    "likes": info.get("like_count", 0),
                    "comments": info.get("comment_count", 0),
                    "creator": username,
                    "url": url
                }
        except Exception as e:
            logger.debug(f"yt-dlp metadata fetch failed for {shortcode}: {e}")
        return None

    async def _scrape_reels(self, page, username: str) -> List[Dict[str, Any]]:
        """Scrape reels using a hybrid Grid + yt-dlp approach."""
        reels_data = []
        
        try:
            url = f"https://www.instagram.com/{username}/reels/"
            logger.info(f"Navigating to {url}")
            await page.goto(url, wait_until="networkidle")
            await self._human_sleep(5, 10)
            
            # Limited scrolling to avoid login wall
            for i in range(2):
                await page.keyboard.press("PageDown")
                await self._human_sleep(2, 4)
            
            grid_reels = await self._scrape_reels_from_grid(page)
            logger.info(f"Found {len(grid_reels)} candidate reels in grid for @{username}.")
            
            # Sort by views and take top 5 to verify with yt-dlp
            grid_reels.sort(key=lambda x: x["views"], reverse=True)
            for candidate in grid_reels[:5]:
                if candidate["views"] < 1000000: continue # Only process if high potential
                
                logger.info(f"Checking virality for {candidate['shortcode']} (Grid Views: {candidate['views']})")
                deep = await self._fetch_deep_metrics(candidate["shortcode"], username)
                
                views = candidate["views"]
                likes = 0
                comments = 0
                
                if deep:
                    views = deep["views"] or candidate["views"]
                    likes = deep["likes"]
                    comments = deep["comments"]
                
                # If grid says 1M+ or yt-dlp confirms it, it's viral
                if views >= 1000000:
                    reels_data.append({
                        "url": f"https://www.instagram.com/reel/{candidate['shortcode']}/",
                        "shortcode": candidate["shortcode"],
                        "view_count": views,
                        "like_count": likes,
                        "comment_count": comments,
                        "creator": username
                    })
                    logger.info(f"🔥 Viral confirmed! @{username}/{candidate['shortcode']} - {views} views")
        except Exception as e:
            logger.error(f"Reel scraping for @{username} failed: {e}")
        
        return reels_data

    async def run(self):
        # Phase 0: Discovery (Already seeded from files)
        # await self._google_search_discovery() # Removed incorrect tool-as-module import

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS)
            )
            page = await context.new_page()
            await stealth_async(page)
            
            # Use a copy to avoid mutating the original set while iterating
            queue = list(self.discovered_accounts)
            
            while queue and len(self.elite_accounts) < self.target_accounts:
                username = queue.pop(0)
                if username in self.processed_accounts: continue
                self.processed_accounts.add(username)
                
                logger.info(f"Processing @{username} (Elite found: {len(self.elite_accounts)}/{self.target_accounts})")
                
                try:
                    await page.goto(f"https://www.instagram.com/{username}/", wait_until="networkidle")
                    await self._human_sleep(1, 3)
                    
                    followers = await self._get_follower_count(page)
                    if followers >= 1000000:
                        logger.info(f"✅ Elite Creator Found! @{username} has {followers} followers.")
                        self.elite_accounts[username] = followers
                        
                        suggested = await self._extract_suggested_accounts(page)
                        for s in suggested:
                            if s not in self.processed_accounts and s not in self.discovered_accounts:
                                self.discovered_accounts.add(s)
                                queue.append(s)
                        
                        viral = await self._scrape_reels(page, username)
                        for v in viral:
                            if not any(r['shortcode'] == v['shortcode'] for r in self.viral_reels):
                                self.viral_reels.append(v)
                                logger.info(f"🔥 Viral Reel Found! @{username} - {v['view_count']} views")
                    
                    if len(self.processed_accounts) % 50 == 0:
                        self._save_state()
                        
                except Exception as e:
                    logger.error(f"Failed to process @{username}: {e}")
                
            await browser.close()
            await self._finalize()

    def _save_state(self):
        state = {
            "elite_accounts": self.elite_accounts,
            "viral_reels": self.viral_reels,
            "processed_accounts": list(self.processed_accounts)
        }
        with open("data/discovery_state.json", "w") as f:
            json.dump(state, f, indent=2)
        self._update_yaml()

    def _update_yaml(self):
        yaml_path = project_root / "config" / "discovered_elite_creators.yaml"
        data = {"discovered_creators": []}
        # Discovered elites from state
        for user, followers in self.elite_accounts.items():
            data["discovered_creators"].append({
                "platform": "instagram",
                "type": "creator",
                "value": user,
                "importance": "high" if followers >= 5000000 else "normal",
                "followers": followers,
                "last_checked": datetime.now().isoformat()
            })
        try:
            with open(yaml_path, "w") as f:
                yaml.dump(data, f)
            logger.info(f"Updated YAML persistence: {len(data['discovered_creators'])} elite accounts.")
        except Exception as e:
            logger.error(f"Failed to update YAML: {e}")

    async def _finalize(self):
        logger.info(f"Finalizing: {len(self.elite_accounts)} elites, {len(self.viral_reels)} reels.")
        
        # Select top 500 by views (some might be proxy views)
        self.viral_reels.sort(key=lambda x: x.get('view_count', 0), reverse=True)
        limit = int(self.target_reels)
        top_500 = self.viral_reels[:limit]
        
        logger.info(f"Selected top {len(top_500)} reels for Drive upload.")
        
        folder_name = f"Scaling_Watcher_Batch_{datetime.now().strftime('%Y%m%d_%H%M')}"
        
        for i, reel in enumerate(top_500):
            logger.info(f"Uploading reel {i+1}/{len(top_500)}: {reel['url']}")
            dl_result = self.downloader.download(reel['url'], filename_hint=f"{reel['creator']}_{reel['shortcode']}")
            if dl_result.success:
                caption = f"Creator: @{reel['creator']}\nViews: {reel['view_count']}\nLikes: {reel['like_count']}\nComments: {reel['comment_count']}\nURL: {reel['url']}"
                self.drive_service.upload_reel(
                    video_path=str(dl_result.video_path),
                    caption=caption,
                    title=f"{folder_name} - {reel['creator']} - {reel['shortcode']}"
                )
            else:
                logger.warning(f"Failed to download {reel['url']}: {dl_result.error}")

if __name__ == "__main__":
    target_acc = int(os.environ.get("TARGET_ACCOUNTS", 10000))
    target_rls = int(os.environ.get("TARGET_REELS", 500))
    seeds = ["batch_creators_google.txt", "batch_creators_2.txt", "batch_creators_3.txt", "batch_creators_4.txt"]
    engine = MassDiscoveryEngine(seeds, target_accounts=target_acc, target_reels=target_rls)
    asyncio.run(engine.run())
