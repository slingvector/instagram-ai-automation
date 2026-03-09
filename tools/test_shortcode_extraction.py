import os
import sys

# Ensure the src directory is in the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.publishing_edge.services.appium_posting_service import AppiumPostingService

def main():
    print("🚀 Initializing AppiumPostingService for testing...")
    service = AppiumPostingService()
    
    print("📱 Attempting to extract recent Reel shortcode via Appium...")
    shortcode = service.grab_recent_reel_shortcode()
    
    if shortcode:
        print(f"\n✅ SUCCESS! Extracted Shortcode: {shortcode}")
    else:
        print("\n❌ FAILED. Could not extract shortcode.")

if __name__ == "__main__":
    main()
