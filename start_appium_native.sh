#!/bin/bash
# Start Native Appium with explicitly defined Homebrew Android SDK paths
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
export ANDROID_SDK_ROOT=/opt/homebrew/share/android-commandlinetools
export PATH=$PATH:/opt/homebrew/bin:/opt/homebrew/share/android-commandlinetools/platform-tools

# Fallback in case just platform-tools are installed w/o the full SDK
if [ ! -d "$ANDROID_HOME" ]; then
    export ANDROID_HOME=/opt/homebrew/Caskroom/android-platform-tools/35.0.0
    export ANDROID_SDK_ROOT=/opt/homebrew/Caskroom/android-platform-tools/35.0.0
fi

echo "Starting Appium with ANDROID_HOME=$ANDROID_HOME"
npx appium --base-path /wd/hub > /tmp/appium.log 2>&1
