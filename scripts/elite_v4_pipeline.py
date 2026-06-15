import os
import re
import json
import yaml
import asyncio
import logging
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Any, Optional
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Add project root to sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from src.ingestion.base import Platform
from src.ingestion.downloader import UniversalDownloader
from src.ingestion.dedup import ContentDedup
from src.ingestion.services.immersive_classifier import ImmersiveClassifier
from src.utils.google_drive_service import GoogleDriveService

# Configuration Constants
CONFIG_PATH = "config/elite_v4_discovery.yaml"
MANIFEST_PATH = "config/elite_v4_manifest.yaml"
DB_PATH = Path("data/elite_v4_dedup.db")
LOG_PATH = "logs/elite_v4.log"

# Setup Isolated Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("EliteV4")

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

class EliteV4Pipeline:
    def __init__(self, target_accounts: int = 10000, target_reels: int = 500):
        self.target_accounts = target_accounts
        self.target_reels = target_reels
        
        self.config = self._load_yaml(CONFIG_PATH)
        self.manifest = self._load_yaml(MANIFEST_PATH)
        
        # Isolated Infrastructure
        self.dedup = ContentDedup(db_path=DB_PATH)
        self.classifier = ImmersiveClassifier()
        self.downloader = UniversalDownloader(output_dir=Path("data/downloads/elite_v4"))
        self.drive_service = GoogleDriveService()
        
        self.elite_accounts: Dict[str, int] = {} # username -> followers
        self.viral_reels: List[Dict[str, Any]] = []
        self.processed_accounts: Set[str] = set()
        self.discovered_queue: List[str] = []
        
        self._seed_discovery()

    def _load_yaml(self, path: str) -> Dict[str, Any]:
        p = Path(path)
        if not p.exists(): return {}
        with open(p, "r") as f:
            return yaml.safe_load(f) or {}

    def _save_yaml(self, path: str, data: Dict[str, Any]):
        with open(path, "w") as f:
            yaml.dump(data, f, sort_keys=False)

    def _seed_discovery(self):
        # Load from manifest if any existing
        for c in self.manifest.get("discovered_creators", []):
            self.elite_accounts[c["value"]] = c.get("followers", 0)
            self.processed_accounts.add(c["value"])
            
        # Load queue from manifest
        self.discovered_queue = self.manifest.get("pending_queue", [])
        
        # Add from config sources if not already processed
        for s in self.config.get("sources", []):
            if s.get("platform") == "instagram" and s.get("type") == "creator":
                val = s["value"]
                if val not in self.processed_accounts and val not in self.discovered_queue:
                    self.discovered_queue.append(val)
            
        logger.info(f"🚀 Elite V4 Seeded: {len(self.discovered_queue)} in queue, {len(self.elite_accounts)} already known.")

    async def _human_sleep(self, min_val: float = 2.0, max_val: float = 5.0):
        await asyncio.sleep(random.uniform(min_val, max_val))

    async def _get_follower_count(self, page) -> int:
        try:
            content = await page.evaluate("""() => {
                let meta = document.querySelector('meta[name="description"]');
                return meta ? meta.content : "";
            }""")
            m = re.search(r'([\d\.,]+[kKmM]?)\s+Followers', content, re.IGNORECASE)
            if m:
                val_str = m.group(1).upper().replace(',', '')
                if 'M' in val_str: return int(float(val_str.replace('M', '')) * 1000000)
                if 'K' in val_str: return int(float(val_str.replace('K', '')) * 1000)
                return int(val_str)
        except: pass
        return 0

    async def _extract_suggested(self, page) -> Set[str]:
        suggested = set()
        try:
            # 1. Try to click the "Suggested" button (Chevron down next to Follow)
            # Many profiles have a button with aria-label="Similar accounts" or "Suggested"
            try:
                suggest_btn = await page.wait_for_selector('div[role="button"][aria-label*="Similar"], div[role="button"][aria-label*="Suggested"]', timeout=3000)
                if suggest_btn:
                    await suggest_btn.click()
                    await self._human_sleep(1.5, 3)
            except: pass

            # 2. Extract usernames from the newly revealed carousel/list
            selectors = [
                'a[href^="/"] span', # Text inside links
                'div[role="button"] span', # Buttons
                'a[href^="/"][role="link"]', # Direct links
                'div[role="dialog"] a[href^="/"]' # If a dialog opened
            ]
            for selector in selectors:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    try:
                        text = await el.inner_text()
                        if text and text.strip().islower() and ' ' not in text:
                            u = text.strip().lower()
                            if len(u) > 2 and u not in ['explore', 'reels', 'about', 'help', 'privacy', 'terms', 'threads', 'profile', 'accounts', 'emails']:
                                suggested.add(u)
                    except: continue
            
            # 3. Last fallback: all top-level links
            links = await page.query_selector_all('a[href^="/"]')
            for link in links:
                href = await link.get_attribute("href")
                if href:
                    parts = href.strip('/').split('/')
                    if len(parts) == 1:
                        u = parts[0]
                        if len(u) > 2 and u not in ['explore', 'reels', 'about', 'help', 'privacy', 'terms', 'threads']:
                            suggested.add(u)
        except Exception as e:
            logger.debug(f"Suggested error: {e}")
        return suggested

    def _parse_metric(self, text: str) -> int:
        if not text: return 0
        text = text.upper().replace(',', '').strip()
        m = re.search(r'([\d.]+)([KM]?)', text)
        if not m: return 0
        v, unit = m.groups()
        v = float(v)
        if unit == 'M': v *= 1000000
        elif unit == 'K': v *= 1000
        return int(v)

    def _is_niche_compliant(self, text: str) -> bool:
        """Strict niche check using ImmersiveClassifier."""
        res = self.classifier.classify(text)
        # We want high-immersion adrenaline OR specific sports/adrenaline categories
        return res["immersion_score"] >= 0.6 or res["type"] != "general_adrenaline"

    async def _scrape_reels_grid(self, page, username: str) -> List[Dict[str, Any]]:
        reels = []
        try:
            elements = await page.query_selector_all('a[href*="/reel/"]')
            for el in elements:
                href = await el.get_attribute("href")
                shortcode = href.strip('/').split('/')[-1]
                all_text = await el.inner_text()
                aria = await el.get_attribute("aria-label") or ""
                
                # Loosen check on grid to avoid missing content with sparse text
                # We will check strictly on deep metadata later
                views = self._parse_metric(f"{all_text} {aria}")
                if views > 0:
                    reels.append({"shortcode": shortcode, "views": views, "creator": username})
        except: pass
        return reels

    async def _fetch_deep_metrics(self, shortcode: str, username: str) -> Optional[Dict[str, Any]]:
        url = f"https://www.instagram.com/reel/{shortcode}/"
        try:
            meta = self.downloader.prefetch_metadata(url)
            if meta and meta.get("success"):
                i = meta.get("metadata", {})
                return {
                    "shortcode": shortcode, "views": i.get("view_count", 0),
                    "likes": i.get("like_count", 0), "comments": i.get("comment_count", 0),
                    "creator": username, "url": url, "title": i.get("title", "")
                }
        except: pass
        return None

    async def run(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
            page = await context.new_page()
            await Stealth().apply_stealth_async(page)
            
            while self.discovered_queue and len(self.elite_accounts) < self.target_accounts:
                user = self.discovered_queue.pop(0)
                if user in self.processed_accounts: continue
                self.processed_accounts.add(user)
                
                logger.info(f"🔍 Checking @{user} ({len(self.elite_accounts)}/{self.target_accounts})")
                try:
                    await page.goto(f"https://www.instagram.com/{user}/", wait_until="networkidle")
                    await self._human_sleep(2, 4)
                    
                    followers = await self._get_follower_count(page)
                    if followers >= 100000: # New threshold: 100k
                        logger.info(f"✅ Elite! @{user} ({followers} followers)")
                        self.elite_accounts[user] = followers
                        
                        # Expand discovery
                        suggested = await self._extract_suggested(page)
                        for s in suggested:
                            if s not in self.processed_accounts and s not in self.discovered_queue:
                                self.discovered_queue.append(s)
                        
                        # Collect Reels
                        await page.goto(f"https://www.instagram.com/{user}/reels/", wait_until="networkidle")
                        await self._human_sleep(3, 6)
                        grid = await self._scrape_reels_grid(page, user)
                        
                        # Verify top candidates
                        grid.sort(key=lambda x: x["views"], reverse=True)
                        for cand in grid[:5]:
                            deep = await self._fetch_deep_metrics(cand["shortcode"], user)
                            if not deep: continue
                            
                            likes = deep["likes"]
                            comments = deep["comments"]
                            views = deep["views"]
                            
                            # New flexible filter: 100k likes OR (10k combined likes+comments)
                            if likes >= 100000 or (likes + comments >= 10000):
                                if self._is_niche_compliant(deep["title"]):
                                    if not any(r["shortcode"] == deep["shortcode"] for r in self.viral_reels):
                                        self.viral_reels.append(deep)
                                        logger.info(f"🔥 Viral! @{user}/{deep['shortcode']} - {likes}L, {comments}C")
                        
                    if len(self.processed_accounts) % 20 == 0:
                        self._save_state()
                        
                except Exception as e:
                    logger.error(f"Error processing @{user}: {e}")
            
            await browser.close()
            await self._finalize()

    def _save_state(self):
        # Update manifest
        creators = []
        for u, f in self.elite_accounts.items():
            creators.append({"platform": "instagram", "type": "creator", "value": u, "followers": f, "importance": "high" if f >= 1000000 else "normal", "last_checked": datetime.now().isoformat()})
        self.manifest["discovered_creators"] = creators
        self.manifest["pending_queue"] = self.discovered_queue
        self._save_yaml(MANIFEST_PATH, self.manifest)
        logger.info(f"💾 State saved. Elites: {len(self.elite_accounts)}, Queue: {len(self.discovered_queue)}, Virals: {len(self.viral_reels)}")

    async def _finalize(self):
        logger.info(f"🏁 Finalizing Elite Run V4. Total Elites: {len(self.elite_accounts)}")
        self.viral_reels.sort(key=lambda x: (x.get('likes', 0) + x.get('comments', 0)), reverse=True)
        top = self.viral_reels[:self.target_reels]
        
        folder = f"Elite_V4_Batch_{datetime.now().strftime('%Y%m%d_%H%M')}"
        for i, r in enumerate(top):
            logger.info(f"📤 Uploading {i+1}/{len(top)}: {r['url']}")
            res = self.downloader.download(r['url'], filename_hint=f"elite_v4_{r['creator']}_{r['shortcode']}")
            if res.success:
                cap = f"Creator: @{r['creator']}\nLikes: {r['likes']}\nComments: {r['comments']}\nViews: {r['views']}\nElite V4 Run"
                self.drive_service.upload_reel(video_path=str(res.video_path), caption=cap, title=f"{folder} - {r['creator']}")
            else:
                logger.warning(f"Download failed for {r['url']}")

if __name__ == "__main__":
    # For demonstration/audit we can use a smaller target initially if needed, 
    # but the user requested 10k accounts and 500 reels.
    pipeline = EliteV4Pipeline(target_accounts=10000, target_reels=500)
    asyncio.run(pipeline.run())
