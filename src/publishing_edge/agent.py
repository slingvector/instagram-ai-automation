"""
MCR Publishing Edge — Agent Entry Point

Usage:
  # Connect device first (WiFi):
  adb connect <device-ip>:5555

  # Start Appium server:
  docker compose -f docker-compose.appium.yml up -d

  # Run the agent:
  python -m src.publishing_edge.agent
"""
import logging
import signal
import sys

from src.publishing_edge.config import FIRESTORE_POLL_INTERVAL_SECONDS, HUMAN_REVIEW_ENABLED
from src.publishing_edge.services.firestore_listener_service import FirestoreListenerService

# Structured JSON-style logging (per BACKEND_STANDARDS.md observability)
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "msg": "%(message)s"}',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main():
    logger.info(
        f"MCR Publishing Edge Agent starting. "
        f"Poll interval: {FIRESTORE_POLL_INTERVAL_SECONDS}s, "
        f"Human review: {'ENABLED' if HUMAN_REVIEW_ENABLED else 'DISABLED (auto-post)'}."
    )

    listener = FirestoreListenerService()

    # Graceful shutdown on SIGINT / SIGTERM
    def handle_signal(sig, frame):
        logger.info(f"Signal {sig} received. Shutting down gracefully...")
        listener.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    listener.start()


if __name__ == "__main__":
    main()
