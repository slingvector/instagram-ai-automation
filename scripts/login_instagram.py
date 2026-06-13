from playwright.sync_api import sync_playwright
import time
from pathlib import Path

def login():
    print("Launching browser... Please log into Instagram.")
    with sync_playwright() as p:
        persistent_dir = Path("data/browser_session")
        persistent_dir.mkdir(parents=True, exist_ok=True)
        
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(persistent_dir),
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            headless=False # Visible browser!
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.instagram.com/accounts/login/")
        
        print("\n" + "="*50)
        print("BROWSER OPENED!")
        print("1. Please log into your Instagram account in the opened window.")
        print("2. Once you are successfully logged in and see the feed, close the browser window.")
        print("="*50 + "\n")
        
        # Wait indefinitely until the user closes the browser context
        try:
            while context.pages:
                time.sleep(1)
        except Exception:
            pass
            
        print("Browser closed. Session saved to 'data/browser_session'!")

if __name__ == "__main__":
    login()
