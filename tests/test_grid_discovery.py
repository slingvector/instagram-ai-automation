import asyncio
import logging
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from scripts.mass_discovery import MassDiscoveryEngine
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_single_account(username):
    seeds = []
    engine = MassDiscoveryEngine(seeds, target_accounts=1, target_reels=5)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await stealth_async(page)
        
        logger.info(f"Testing @{username}...")
        viral_reels = await engine._scrape_reels(page, username)
        
        logger.info(f"Found {len(viral_reels)} viral reels for @{username}:")
        for r in viral_reels:
            logger.info(f" - {r['url']} | Views: {r['view_count']} | Likes: {r['like_count']}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_single_account("thebucketlistfamily"))
