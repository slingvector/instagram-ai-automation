#!/bin/bash
# run_publishing_edge.sh
# ----------------------
# Bootstraps the Mac Mini (Edge Node) to execute Instagram automation.
# Can be run manually or tied to macOS launchd for automatic startup on boot.

# Change directory exactly to where this script resides, then move up to project root
cd "$(dirname "$0")"/.. || exit

echo "[Edge Boot] Starting Mac Mini Publishing Edge Node..."

# 1. Kill any existing ADB server to prevent port conflicts
echo "[Edge Boot] Restarting ADB daemon on host 0.0.0.0 for Docker..."
adb kill-server
# Start ADB nodaemon in the background and discard its endless logs
nohup adb -a nodaemon server start >/dev/null 2>&1 &
sleep 2

# 2. Boot the Appium Server via Docker Compose
echo "[Edge Boot] Starting Appium Docker Container..."
docker compose -f docker-compose.appium.yml up -d
sleep 3

# 3. Start the Firestore Long-Polling Listener in Python
echo "[Edge Boot] Activating Python Virtual Environment & Firestore Daemon..."
source venv/bin/activate
export PYTHONPATH=.
python -c "from src.publishing_edge.services.firestore_listener_service import FirestoreListenerService; FirestoreListenerService().start()"
