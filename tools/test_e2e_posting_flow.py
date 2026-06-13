import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.publishing_edge.services.appium_posting_service import AppiumPostingService

def main():
    service = AppiumPostingService()
    
    print("\n" + "="*50)
    print("🚀 FLOW A: Reel Upload Phase")
    print("="*50)
    print("📱 Stage 1: Preparing Reel Post...")
    caption = "Modular E2E test! Testing separate upload/extraction cycles. #e2etest #automation"
    
    # Block A: Upload Flow
    # prepare_reel_post -> share_post
    try:
        if service.prepare_reel_post("/sdcard/Movies/test.mp4", caption):
            print("✅ Stage 1 complete. Reel draft staged.")
            print("📱 Stage 2: Tapping Share...")
            service.share_post()
            print("✅ Stage 2 complete. Reel shared successfully.")
        else:
            print("❌ FAILED: Could not stage Reel draft.")
            return
    except Exception as e:
        print(f"❌ FAILED during Flow A: {e}")
        return

    # App is now closed (end_session was called in share_post finally block)
    print("\n" + "~"*50)
    print("⏳ Waiting 30 seconds for Meta to finalize and index the Reel...")
    print("~"*50)
    time.sleep(30)
    
    print("\n" + "="*50)
    print("🚀 FLOW B: Shortcode Extraction Phase")
    print("="*50)
    print("📱 Stage 3: Extracting Shortcode from profile (Fresh Cold Start)...")
    
    # Block B: Extraction Flow
    # grab_recent_reel_shortcode starts its own fresh session
    try:
        shortcode = service.grab_recent_reel_shortcode()
        if shortcode:
            print(f"\n🎉 SUCCESS! Modular E2E Complete. Extracted: {shortcode}")
        else:
            print("\n❌ FAILED: Extraction step returned None.")
    except Exception as e:
        print(f"❌ FAILED during Flow B: {e}")

if __name__ == "__main__":
    main()
