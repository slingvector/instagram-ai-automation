import asyncio
import random
import logging
from urllib.parse import urlparse
from typing import Set

from playwright.async_api import async_playwright, Page, BrowserContext
from playwright_stealth import stealth_async

logger = logging.getLogger(__name__)

class PlaywrightScraperService:
    """
    Service layer responsible for interacting with the DOM via Playwright.
    """
    def __init__(self, target_url: str, user_data_dir: str, headless: bool = False, proxy_server: str = None):
        self.target_url = target_url
        self.user_data_dir = user_data_dir
        self.headless = headless
        self.proxy_config = {"server": proxy_server} if proxy_server else None

    async def _human_sleep(self, min_val: float = 1.5, max_val: float = 4.2):
        """Simulates human interaction delays to bypass rate-limits."""
        delay = random.uniform(min_val, max_val)
        logger.debug(f"Sleeping for {delay:.2f}s")
        await asyncio.sleep(delay)

    def _extract_reel_url(self, text: str) -> str:
        """Extracts the first valid instagram reel URL from a given text block."""
        if not text:
            return None
        words = text.split()
        for word in words:
            if "instagram.com/reel/" in word:
                parsed = urlparse(word)
                base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                return base_url
        return None

    async def get_new_reel_urls(self) -> Set[str]:
        """
        Launches browser, navigates to DMs, and extracts all visible Reel URLs.
        Returns a set of unique URLs found in the DOM.
        """
        extracted_urls = set()
        logger.info("Initializing Stealth DM Scraper...")

        async with async_playwright() as p:
            args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox"
            ]
            
            # Load persistent context
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                proxy=self.proxy_config,
                args=args,
                viewport={"width": 1280, "height": 800}
            )
            
            page = context.pages[0] if context.pages else await context.new_page()
            await stealth_async(page)
            
            logger.info("Navigating to Instagram Direct Messages...")
            try:
                await page.goto(self.target_url, wait_until="networkidle")
                await self._human_sleep(3.0, 5.0)
                
                # Check for login redirect indicating expired session
                if "/accounts/login/" in page.url:
                    logger.error("Session expired! Run script in non-headless mode to log in manually.")
                    return extracted_urls

                logger.info("Looking for Reel URLs in the chat...")
                message_elements = await page.query_selector_all('div[role="button"] span, div[dir="auto"]')
                
                for el in message_elements:
                    text = await el.inner_text()
                    reel_url = self._extract_reel_url(text)
                    if reel_url:
                        extracted_urls.add(reel_url)
                        
            except Exception as e:
                logger.error(f"Error during scraping session: {e}", exc_info=True)
            finally:
                logger.info("Closing browser context.")
                await context.close()
                
        return extracted_urls
