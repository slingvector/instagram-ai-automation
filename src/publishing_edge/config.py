import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

BASE_DIR = Path(__file__).parent.parent.parent

# Appium / ADB
APPIUM_HOST = os.getenv("APPIUM_HOST", "http://localhost:4723")
DEVICE_UDID = os.getenv("DEVICE_UDID", "")  # blank = auto-detect first available device
INSTAGRAM_PACKAGE = os.getenv("INSTAGRAM_PACKAGE", "com.instagram.android")
INSTAGRAM_ACTIVITY = os.getenv("INSTAGRAM_ACTIVITY", "com.instagram.mainactivity.InstagramMainActivity")
NEW_COMMAND_TIMEOUT = int(os.getenv("NEW_COMMAND_TIMEOUT", "3600"))

# Firestore Listener
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "mcr-relay-1772228380")
FIRESTORE_POLL_INTERVAL_SECONDS = int(os.getenv("FIRESTORE_POLL_INTERVAL_SECONDS", "30"))
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

# GCS (for downloading processed video before posting)
GCS_PROCESSED_BUCKET = os.getenv("GCS_PROCESSED_BUCKET", "mcr-relay-1772228380-raw-input")

# Human Review
# When True, agent pauses after filling post form and waits for operator to confirm via Firestore
HUMAN_REVIEW_ENABLED = os.getenv("HUMAN_REVIEW_ENABLED", "true").lower() == "true"
