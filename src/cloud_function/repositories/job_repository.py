from google.cloud import firestore
import logging
import uuid
import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

class JobRepository:
    """
    Repository layer for managing Firestore pipeline state operations.
    Follows Single Responsibility and Dependency Inversion.
    """
    def __init__(self, project_id: str, collection_name: str = "job_queue"):
        self.project_id = project_id
        self.collection_name = collection_name
        try:
            self.db = firestore.Client(project=self.project_id)
            logger.info(f"Connected to Firestore Project: {self.project_id}")
        except Exception as e:
            logger.error(f"Failed to connect to Firestore: {e}")
            raise

    def create_job(self, gcs_uri: str, metadata: Dict[str, Any]) -> str:
        """
        Creates a new document in the job_queue collection linking the raw video
        with its generated AI metadata.
        Returns the new document ID.
        """
        try:
            job_id = str(uuid.uuid4())
            doc_ref = self.db.collection(self.collection_name).document(job_id)
            
            payload = {
                "job_id": job_id,
                "gcs_raw_video_uri": gcs_uri,
                "ai_metadata": metadata,
                "status": "PENDING_MEDIA_FACTORY",
                "created_at": datetime.datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.datetime.utcnow().isoformat() + "Z"
            }
            
            doc_ref.set(payload)
            logger.info(f"Successfully created Firestore job document: {job_id}")
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to write to Firestore: {e}")
            raise

    def update_job(self, job_id: str, data: Dict[str, Any]):
        """
        Updates an existing job document with new data (e.g., processed_uri, status).
        """
        try:
            doc_ref = self.db.collection(self.collection_name).document(job_id)
            data["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
            doc_ref.update(data)
            logger.info(f"Successfully updated Firestore job document: {job_id}")
        except Exception as e:
            logger.error(f"Failed to update Firestore job {job_id}: {e}")
            raise
