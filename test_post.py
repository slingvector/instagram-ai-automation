import os
from google.cloud import firestore
from src.publishing_edge.controllers.posting_controller import PostingController
from src.publishing_edge.services.adb_client import ADBClient
import logging
import time

logging.basicConfig(level=logging.INFO)

job_id = "bd2a6441-7356-4db0-b08e-b826b0a67236"
db = firestore.Client(project="mcr-relay-1772228380")

print("Resetting job...")
db.collection("job_queue").document(job_id).update({"status": "READY_FOR_PUBLISHING"})

print("Force stopping Instagram...")
ADBClient().stop_instagram()
time.sleep(2)

print("Executing PostingController...")
controller = PostingController()
controller.execute(job_id)
print("Finished!")
