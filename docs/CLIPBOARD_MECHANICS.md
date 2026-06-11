# Clipboard Implementation Mechanics

This document details how the MCR Publishing Edge handles text input via the Android clipboard for Instagram, TikTok, and YouTube Shorts automation.

## 📋 Architecture
The system uses a multi-layered approach to ensure text (captions, hashtags, descriptions) is reliably entered into mobile input fields, even when standard Appium `send_keys` fails due to complex UI overlays.

### 1. The `AppiumPostingService` Implementation
Location: `src/publishing_edge/services/appium_posting_service.py`

#### Copy (Set Clipboard)
The system tries to set the device clipboard using two methods:
1. **Primary**: `self._driver.set_clipboard_text(text)` (Native Appium).
2. **Fallback**: `adb shell am broadcast -a clipper.set -e text '{text}'`.
   - *Requirement*: This requires the **Clipper** APK to be installed on the device.

#### Paste (Triggering Entry)
Instead of relying on the UI to show a "Paste" bubble, the system forces a system-level paste event:
```python
# Keycode 279 is standard for KEYCODE_PASTE in Android
self._adb._run(["shell", "input", "keyevent", "279"])
```

### 2. Implementation Snippet
```python
def _paste_action(text: str):
    try:
        self._driver.set_clipboard_text(text)
    except Exception:
        # Fallback for older devices or restricted Appium sessions
        self._adb._run(["shell", "am", "broadcast", "-a", "clipper.set", "-e", "text", text])
    
    time.sleep(0.8)
    self._adb._run(["shell", "input", "keyevent", "279"])
```

### 3. Usage Across Platforms
- **Instagram**: Used in `_enter_caption` to handle the Share screen.
- **TikTok**: Used in `crosspost_to_tiktok` for the "Describe your post" field.
- **YouTube Shorts**: Used in `crosspost_to_youtube_shorts` for the "Caption your Short" field.

## 🛠 Troubleshooting
If pasting fails:
1. **Verify Clipper**: Run `adb shell pm list packages | grep clipper`. If missing, install `Clipper.apk`.
2. **Focus Check**: Ensure the target `EditText` or `AutoCompleteTextView` is focused (blinking cursor) before the paste command is issued. The bot attempts to `click()` the field before pasting.
3. **Keycode Compatibility**: Some specialized keyboards (like Samsung or Gboard) may require `CTRL+V` (`keyevent 29 50`). If 279 fails, the ADB client can be extended to support macro-key sequences.

## 🔗 Link Copying (Shortcode Extraction)
Beyond pasting, the bot can programmatically "Copy Link" to track posts.

### The Flow (`grab_recent_reel_shortcode`)
1. **Navigate**: Profile -> Reels Tab -> First Reel.
2. **Share Sheet**: Taps the `direct_share_button` (Paper plane icon).
3. **Action**: Taps **"Copy link"** (includes a horizontal swipe fallback if the button is off-screen).
4. **Read**: Extracts the URL from the clipboard.

### Reading the Clipboard
Location: `_extract_shortcode_from_clipboard()`
1. **Primary**: `self._driver.get_clipboard_text()`.
2. **System Fallback**: `adb shell service call clipboard 2`.
   - *Note*: This returns a serialized parcel which the bot parses to extract the string.
3. **Regex**: The URL is parsed with `r'/(?:reel|p)/([A-Za-z0-9_-]+)/?'` to extract the unique ID for database entry.
