from google.cloud import firestore
import logging
import datetime

logger = logging.getLogger(__name__)

class ProcessedJobRepository:
    """
    Repository layer for managing Firestore pipeline state operations during Media processing.
    """
    def __init__(self, project_id: str, collection_name: str = "job_queue"):
        self.project_id = project_id
        self.collection_name = collection_name
        self.db = firestore.Client(project=self.project_id)
        logger.info(f"Connected to Firestore Project: {self.project_id}")

    def get_job(self, job_id: str) -> dict:
        """Retrieves a job payload by ID."""
        doc_ref = self.db.collection(self.collection_name).document(job_id)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None

    def mark_job_completed(self, job_id: str, processed_uri: str):
        """Updates a job indicating the media has been burned and is ready."""
        try:
           doc_ref = self.db.collection(self.collection_name).document(job_id)
           doc_ref.update({
               "status": "READY_FOR_PUBLISHING",
               "gcs_processed_video_uri": processed_uri,
               "updated_at": datetime.datetime.utcnow().isoformat() + "Z"
           })
           logger.info(f"Successfully updated Firestore job {job_id} to completed.")
        except Exception as e:
            logger.error(f"Failed to update Firestore job {job_id}: {e}")
            raise
