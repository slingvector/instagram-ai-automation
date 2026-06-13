"""
scripts/authenticate_browser.py

This script launches the Playwright browser using the persistent context
used by the scraping adapters (CreatorAdapter, DMAdapter). 
It launches in non-headless mode (visible UI) and keeps the browser open
so the user can manually log in to Instagram, YouTube, Reddit, or any other
platform, handle captchas, and click "Save Login".

Once logged in, the user can close the browser manually, and the authenticated
state will be saved and reused by all headless background scrapes.
"""
from playwright.sync_api import sync_playwright
import os
from pathlib import Path

def run():
    print("🚀 Launching Persistent Browser Session for Authentication...")
    print("Wait for the browser to open, log into your accounts, and close the window when done.")
    
    with sync_playwright() as p:
        persistent_dir = Path("data/browser_session")
        persistent_dir.mkdir(parents=True, exist_ok=True)
        
        context_kwargs = {
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1280, "height": 800},
            "locale": "en-US",
            "device_scale_factor": 2,
            "headless": False, # Force visible
        }
        
        use_proxy = os.environ.get("USE_PROXY_FOR_INGESTION", "false").lower() == "true"
        proxy_url = os.environ.get("PROXY_SERVER")
        
        if use_proxy and proxy_url:
            context_kwargs["proxy"] = {"server": proxy_url}

        context = p.chromium.launch_persistent_context(
            user_data_dir=str(persistent_dir),
            **context_kwargs
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        # Open Instagram by default since it's the most common roadblock
        print("🌍 Opening Instagram... Please log in.")
        try:
            page.goto("https://www.instagram.com/")
        except Exception as e:
            print(f"⚠️ Error navigating to Instagram: {e}")
            
        print("\n\n✅ BROWSER OPEN: You can now log into Instagram, Reddit, YouTube, etc.")
        print("IMPORTANT: Once you are logged in, just CLOSE the browser window manually.")
        
        # Keep the script running until the user closes the context manually
        try:
            page.wait_for_event("close", timeout=0) # 0 = infinite timeout
        except Exception:
            pass
            
        print("Browser closed. Persistent state saved to 'data/browser_session/'.")

if __name__ == "__main__":
    run()
