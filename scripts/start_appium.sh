#!/bin/bash
# start_appium.sh: Industrial-Grade Appium Launcher
# Ensures environment variables from .env are exported to the Appium process.

# 1. Load context
BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
ENV_FILE="$BASE_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    echo "⚙️ Loading environment from $ENV_FILE..."
    # Helper to load and export variables from .env
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "⚠️ Warning: .env not found at $ENV_FILE. Using system environment."
fi

# 2. Hardening: Ensure ANDROID_HOME is set if not already in .env
if [ -z "$ANDROID_HOME" ]; then
    export ANDROID_HOME="/Users/cortex/Library/Android/sdk"
fi

# 3. Path injection: Ensure adb and other tools are visible
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/tools:$ANDROID_HOME/tools/bin:$PATH"

echo "📍 ANDROID_HOME: $ANDROID_HOME"
echo "📍 APPIUM_HOST: $APPIUM_HOST"

# 4. Clean up stale Appium processes holding the port
echo "♻️ Cleaning up stale Appium processes..."
pkill -f appium || true
sleep 1

# 5. Launch Appium with industrial-scale configuration
echo "🚀 Starting Appium Server..."
exec appium --address 127.0.0.1 --port 4723 --use-plugins execute-driver --base-path /wd/hub
