import os
from pathlib import Path
import time
from playwright.sync_api import sync_playwright

def login():
    persistent_dir = Path("data/browser_session")
    persistent_dir.mkdir(parents=True, exist_ok=True)
    
    with sync_playwright() as p:
        print("Launching browser... Please log in to Instagram.")
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(persistent_dir),
            headless=False,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = browser.new_page()
        page.goto("https://www.instagram.com/accounts/login/")
        
        print("Waiting up to 120 seconds for you to log in...")
        try:
            # Wait until we see the home icon or something indicating login success
            page.wait_for_selector("svg[aria-label='Home']", timeout=120000)
            print("Login successful! Saving session...")
            
            # Export cookies to data/ig_cookies.json
            import json
            cookies = browser.cookies()
            with open("data/ig_cookies.json", "w") as f:
                json.dump(cookies, f)
            print("Cookies saved to data/ig_cookies.json.")
            
        except Exception as e:
            print(f"Timeout or error: {e}. If you logged in successfully, the session is still saved.")
        
        print("Closing browser in 5 seconds...")
        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    login()
