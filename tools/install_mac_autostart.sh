#!/bin/bash
# install_mac_autostart.sh
# ------------------------
# Generates and installs a macOS LaunchAgent to ensure the Publishing Edge
# automaticaly runs 24/7 in the background when this Mac Mini boots up.

PROJECT_DIR=$(cd "$(dirname "$0")"/.. && pwd)
PLIST_PATH="$HOME/Library/LaunchAgents/com.mcr.publishing.edge.plist"
SCRIPT_PATH="$PROJECT_DIR/tools/run_publishing_edge.sh"

echo "[MCR Installer] Creating LaunchAgent at: $PLIST_PATH"

cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.mcr.publishing.edge</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SCRIPT_PATH</string>
    </array>
    
    <!-- Run once automatically when the user logs in -->
    <key>RunAtLoad</key>
    <true/>
    
    <!-- Keep it running forever, restarting if it ever crashes -->
    <key>KeepAlive</key>
    <true/>
    
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    
    <!-- Logging paths -->
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/data/edge_service.err</string>
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/data/edge_service.out</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
EOF

echo "[MCR Installer] LaunchAgent created."
echo "Loading the agent into macOS launchd..."

# Unload the old version if it exists, then load the new one
launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH"

echo "✅ Success! The MCR Publishing Edge is now a permanent background daemon."
echo "Check logs anytime via: tail -f $PROJECT_DIR/data/edge_service.out"
