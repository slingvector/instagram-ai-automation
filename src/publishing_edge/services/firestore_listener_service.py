import logging
import time
from google.cloud import firestore

from src.publishing_edge.config import GCP_PROJECT_ID, FIRESTORE_POLL_INTERVAL_SECONDS
from src.publishing_edge.controllers.posting_controller import PostingController

logger = logging.getLogger(__name__)

# Firestore statuses this agent watches for
TRIGGER_STATUS = "READY_FOR_PUBLISHING"
LOCK_STATUS = "POSTING_IN_PROGRESS"  # set atomically to prevent double-pick


class FirestoreListenerService:
    """
    Polls Firestore for jobs with status='ready_to_post' and triggers
    the PostingController for each one.

    Design decisions (per BACKEND_STANDARDS.md):
    - Processes ONE job at a time to avoid Appium session conflicts (Singleton)
    - Uses optimistic locking: sets status='posting' before processing
      to prevent duplicate execution if multiple agents ever run
    - Exponential backoff on Firestore errors (fault tolerance)
    - Structured logging with job_id correlation
    """

    def __init__(self):
        self.db = firestore.Client(project=GCP_PROJECT_ID)
        self.controller = PostingController()
        self._running = False

    def start(self):
        """Start the blocking listener loop. Runs until stop() is called."""
        self._running = True
        logger.info(
            f"Firestore listener started. "
            f"Polling every {FIRESTORE_POLL_INTERVAL_SECONDS}s for '{TRIGGER_STATUS}' in 'job_queue'."
        )
        backoff = FIRESTORE_POLL_INTERVAL_SECONDS
        while self._running:
            try:
                self._tick()
                backoff = FIRESTORE_POLL_INTERVAL_SECONDS  # reset backoff on success
            except Exception as e:
                logger.error(f"Listener error: {e}. Backing off for {backoff}s.", exc_info=True)
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)  # cap at 5 min
                continue
            time.sleep(FIRESTORE_POLL_INTERVAL_SECONDS)

    def stop(self):
        """Signal the listener loop to stop after the current iteration."""
        self._running = False
        logger.info("Firestore listener stopping...")

    def _tick(self):
        """Single poll cycle: look for one ready job and process it."""
        jobs = (
            self.db.collection("job_queue")
            .where("status", "==", TRIGGER_STATUS)
            .limit(1)
            .stream()
        )

        job_list = list(jobs)
        if not job_list:
            logger.debug("No jobs ready to post.")
            return

        job_doc = job_list[0]
        job_id = job_doc.id

        # Optimistic lock — only process if we successfully claim it
        claimed = self._try_claim(job_id)
        if not claimed:
            logger.warning(f"[{job_id}] Could not claim job — already being processed.")
            return

        logger.info(f"[{job_id}] Claimed job. Handing off to PostingController.")
        self.controller.execute(job_id)

    def _try_claim(self, job_id: str) -> bool:
        """
        Atomically transitions status from 'ready_to_post' → 'posting'.
        Returns True if we successfully claimed the job, False if it was
        already taken (race condition with another agent).
        """
        job_ref = self.db.collection("job_queue").document(job_id)
        try:
            @firestore.transactional
            def claim_in_transaction(transaction):
                snap = job_ref.get(transaction=transaction)
                if snap.to_dict().get("status") != TRIGGER_STATUS:
                    return False
                transaction.update(job_ref, {"status": LOCK_STATUS})
                return True

            transaction = self.db.transaction()
            return claim_in_transaction(transaction)
        except Exception as e:
            logger.error(f"[{job_id}] Claim transaction failed: {e}")
            return False
