#!/bin/bash
# park_pipeline.sh: Safely stop all MCR automation components

echo "🛑 Parking Industrial Reels Pipeline..."

# 1. Terminate the Bulk Poster Runner
if pgrep -f bulk_post.py > /dev/null; then
    echo "Stopping Bulk Poster (bulk_post.py)..."
    pkill -TERM -f bulk_post.py
    sleep 2
else
    echo "Bulk Poster not running."
fi

# 2. Terminate Appium Server
if pgrep -f "appium" > /dev/null; then
    echo "Stopping Appium Server..."
    pkill -9 -f appium
    pkill -9 node
    sleep 1
else
    echo "Appium not running."
fi

# 3. Clean Device State
echo "Cleaning device state (Force-stopping Instagram)..."
adb shell am force-stop com.instagram.android 2>/dev/null

# 4. Final Cleanup
echo "Cleaning up temp files..."
rm -rf /tmp/appium.log 2>/dev/null

echo "✅ Pipeline parked safely. All processes stopped."
