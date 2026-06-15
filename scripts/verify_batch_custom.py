# scripts/verify_batch_custom.py
import yaml
import logging
import asyncio
import json
import os
import re
from pathlib import Path
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Quality Bar
MIN_FOLLOWERS = 0
MIN_POSTS = 0

# Load accounts from the manifest
import os
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "indian_models_manifest.yaml")
TARGET_ACCOUNTS = []
if os.path.exists(MANIFEST_PATH):
    with open(MANIFEST_PATH, "r") as f:
        doc = yaml.safe_load(f)
        for src in doc.get("sources", []):
            TARGET_ACCOUNTS.append(src["value"])
else:
    logger.error(f"Manifest not found: {MANIFEST_PATH}")

def parse_count(f_str: str) -> int:
    f_str = f_str.strip().upper().replace(",", "")
    try:
        if 'K' in f_str:
            return int(float(f_str.replace('K', '')) * 1000)
        elif 'M' in f_str:
            return int(float(f_str.replace('M', '')) * 1000000)
        elif 'B' in f_str:
            return int(float(f_str.replace('B', '')) * 1000000000)
        else:
            return int(f_str)
    except ValueError:
        return 0

async def get_ig_metadata_with_cookies(page, username):
    url = f"https://www.instagram.com/{username}/"
    try:
        logger.info(f"Navigating to {url}...")
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(3)
        
        # Try to extract content from meta tags first (fastest)
        meta_desc = await page.get_attribute("meta[name='description']", "content")
        logger.info(f"Meta description: {meta_desc}")
        
        followers = 0
        posts = 0
        
        if meta_desc:
            # Example: "1.2M Followers, 300 Following, 1,450 Posts - See Instagram photos and videos from ..."
            f_match = re.search(r"([\d\.,]+[KMBkmb]?) Followers", meta_desc, re.IGNORECASE)
            if f_match:
                followers = parse_count(f_match.group(1))
            
            p_match = re.search(r"([\d\.,]+[KMBkmb]?) Posts", meta_desc, re.IGNORECASE)
            if p_match:
                posts = parse_count(p_match.group(1))
                
        # Fallback if meta description doesn't work (e.g. login wall or different page layout)
        if followers == 0 or posts == 0:
            logger.info("Meta description parsing failed/incomplete. Trying page selectors...")
            try:
                # Look for links containing "/followers/" or "/posts/"
                # Wait a bit to ensure full load
                await page.wait_for_selector("a[href*='/followers/']", timeout=5000)
                followers_text = await page.locator("a[href*='/followers/']").first.inner_text()
                # e.g., "1.2M followers" or "10k followers" or "100 followers"
                f_match = re.search(r"([\d\.,]+[KMBkmb]?)", followers_text)
                if f_match:
                    followers = parse_count(f_match.group(1))
            except Exception as e:
                logger.debug(f"Follower selector failed: {e}")
                
            try:
                # Posts count usually isn't a link, or is in the header
                posts_text = await page.locator("header li").first.inner_text()
                # e.g. "1,450 posts"
                p_match = re.search(r"([\d\.,]+[KMBkmb]?)", posts_text)
                if p_match:
                    posts = parse_count(p_match.group(1))
            except Exception as e:
                logger.debug(f"Posts selector failed: {e}")
                
        # If still 0, check if the account name is actually visible
        page_title = await page.title()
        if "Page Not Found" in page_title or "Page not found" in page_title:
            logger.error(f"Account @{username} not found (404 Page Not Found).")
            return {"followers": 0, "posts": 0, "username": username, "status": "NOT_FOUND"}

        return {"followers": followers, "posts": posts, "username": username, "status": "SUCCESS"}
    except Exception as e:
        logger.error(f"Failed to verify IG @{username}: {e}")
        return None

async def main():
    logger.info("Initializing Custom IG Auditor...")
    cookie_path = Path("data/ig_cookies.json")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        if cookie_path.exists():
            try:
                with open(cookie_path, "r") as f:
                    cookies = json.load(f)
                    await context.add_cookies(cookies)
                logger.info(f"Successfully loaded {len(cookies)} cookies from {cookie_path}")
            except Exception as e:
                logger.warning(f"Could not load cookies: {e}")
        else:
            logger.warning(f"No cookies found at {cookie_path}. Proceeding without authentication.")
            
        page = await context.new_page()
        
        results = []
        for idx, username in enumerate(TARGET_ACCOUNTS, 1):
            logger.info(f"[{idx}/{len(TARGET_ACCOUNTS)}] Auditing @{username}...")
            res = await get_ig_metadata_with_cookies(page, username)
            
            if res:
                followers = res.get("followers", 0)
                posts = res.get("posts", 0)
                status = res.get("status", "SUCCESS")
                
                is_valid = followers >= MIN_FOLLOWERS and posts >= MIN_POSTS
                res["is_valid"] = is_valid
                results.append(res)
                
                validation_str = "✅ PASS" if is_valid else "❌ FAIL"
                if status == "NOT_FOUND":
                    validation_str = "🚫 NOT FOUND"
                logger.info(f"Result for @{username}: Followers={followers}, Posts={posts} | Status={validation_str}")
            else:
                results.append({
                    "username": username,
                    "followers": 0,
                    "posts": 0,
                    "status": "ERROR",
                    "is_valid": False
                })
                logger.warning(f"Result for @{username}: Error occurred during fetch.")
                
            # Random jitter delay to mimic human behavior
            await asyncio.sleep(2)
            
        await browser.close()
        
        # Save results to a Markdown file
        output_path = Path("data/audit_results.md")
        with open(output_path, "w") as f:
            f.write("# Instagram Account Audit Results\n\n")
            f.write(f"Target Quality Bar: Followers >= {MIN_FOLLOWERS:,}, Posts >= {MIN_POSTS}\n\n")
            f.write("| Username | Followers | Posts | Status | Audit Verdict |\n")
            f.write("| --- | --- | --- | --- | --- |\n")
            
            passed_count = 0
            for r in results:
                username = r["username"]
                followers = r["followers"]
                posts = r["posts"]
                status = r["status"]
                is_valid = r["is_valid"]
                
                verdict = "✅ PASS" if is_valid else "❌ FAIL"
                if status == "NOT_FOUND":
                    verdict = "🚫 NOT FOUND"
                elif status == "ERROR":
                    verdict = "⚠️ ERROR"
                    
                if is_valid:
                    passed_count += 1
                    
                f.write(f"| @{username} | {followers:,} | {posts} | {status} | {verdict} |\n")
                
            f.write(f"\nSummary: {passed_count} / {len(results)} accounts passed the quality bar.\n")
            
        logger.info(f"Audit completed. Report saved to {output_path}")

if __name__ == "__main__":
    asyncio.run(main())
