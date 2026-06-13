"""
src/config.py

Centralized configuration for the MCR pipeline.
All GCP project IDs, bucket names, and shared settings live here.
Individual modules should import from this file instead of hardcoding values.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ── GCP Core ─────────────────────────────────────────────────────────────────
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

# ── GCS Buckets ──────────────────────────────────────────────────────────────
GCS_BUCKET_RAW = os.getenv("GCS_BUCKET_NAME", "")
GCS_BUCKET_PROCESSED = os.getenv("GCS_PROCESSED_BUCKET", "")

# ── Publishing Edge ──────────────────────────────────────────────────────────
APPIUM_HOST = os.getenv("APPIUM_HOST", "http://localhost:4723")
DEVICE_UDID = os.getenv("DEVICE_UDID", "")
INSTAGRAM_PACKAGE = os.getenv("INSTAGRAM_PACKAGE", "com.instagram.android")
FIRESTORE_POLL_INTERVAL_SECONDS = int(os.getenv("FIRESTORE_POLL_INTERVAL_SECONDS", "30"))
HUMAN_REVIEW_ENABLED = os.getenv("HUMAN_REVIEW_ENABLED", "true").lower() == "true"
REVIEW_TIMEOUT_MINUTES = int(os.getenv("REVIEW_TIMEOUT_MINUTES", "10"))

# ── Ingestion ────────────────────────────────────────────────────────────────
HEADLESS = os.getenv("HEADLESS", "True").lower() == "true"
IG_READONLY_USERNAME = os.getenv("IG_READONLY_USERNAME", "")
IG_READONLY_PASSWORD = os.getenv("IG_READONLY_PASSWORD", "")
IG_SESSION_FILE = os.getenv("IG_SESSION_FILE", "data/ig_readonly_session.json")
