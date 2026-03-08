"""
tools/test_intercept_profile.py
"""
import logging
import json
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_intercept")

def test_intercept(username: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            storage_state="data/ig_readonly_session.json"
        )
        page = context.new_page()
        
        captured_data = []

        def handle_res(response):
            if "graphql" in response.url or "api/v1" in response.url:
                if response.request.resource_type in ["fetch", "xhr"]:
                    try:
                        text = response.text()
                        if len(text) > 5000:
                            captured_data.append(response.url + "\n" + text)
                    except Exception:
                        pass
                        
        page.on("response", handle_res)
        
        url = f"https://www.instagram.com/{username}/reels/"
        logger.info(f"Visiting {url}")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        
        with open("debug/intercepted_profile.json", "w") as f:
            for d in captured_data:
                f.write(d + "\n\n")
                
        logger.info(f"Captured {len(captured_data)} payloads matching criteria. Wrote to debug/intercepted_profile.json")
        browser.close()

if __name__ == "__main__":
    import os
    os.makedirs("debug", exist_ok=True)
    test_intercept("complex")
