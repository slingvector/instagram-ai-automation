"""
tools/test_profile_scrape.py
"""
import logging
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_profile")

def test_scrape(username: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            storage_state="data/ig_readonly_session.json"
        )
        page = context.new_page()
        
        url = f"https://www.instagram.com/{username}/reels/"
        logger.info(f"Visiting {url}")
        
        # Load the page and wait for a tags
        response = page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        
        try:
            # Look for reel links
            links = page.locator("a[href*='/reel/']").all()
            hrefs = []
            for link in links:
                href = link.get_attribute("href")
                if href and href not in hrefs:
                    hrefs.append(href)
                    
            logger.info(f"Found {len(hrefs)} reel links: {hrefs}")
        except Exception as e:
            logger.error(f"Failed to find links: {e}")
            logger.info("Dumping page content snippet...")
            logger.info(page.content()[:1000])
            
        browser.close()

if __name__ == "__main__":
    test_scrape("complex")
