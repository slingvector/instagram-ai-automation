import sys
import os
import logging
from flask import Flask

# Ensure the src folder is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.media_factory.controllers.factory_controller import process_job

logging.basicConfig(level=logging.INFO)

def test_media_factory_integration():
    print("Triggering Media Factory Controller...")
    
    # Needs a real job_id that currently exists in the Firestore database
    job_id = "bd2a6441-7356-4db0-b08e-b826b0a67236"
    
    # Note: Ensure the raw_video_uri exists in the bucket
    from google.cloud import firestore
    db = firestore.Client(project="mcr-relay-1772228380")
    
    # Pre-configure the mock job in firestore for the test
    db.collection("job_queue").document(job_id).set({
        "status": "RAW_DOWNLOADED",
        "gcs_raw_video_uri": "gs://mcr-relay-1772228380-raw-input/raw_video.mp4",
        "ai_metadata": {
            "burn_in_text": "Web3 Test Burn",
            "caption": "MCR Blockchain Integration Test #web3 #automation"
        }
    }, merge=True)
    
    # Process the job
    try:
        response, status_code = process_job(job_id)
        print(f"\nStatus Code: {status_code}")
        print(f"Response: {response.get_json()}")
        
        # Verify Firestore has the tx hash
        doc = db.collection("job_queue").document(job_id).get().to_dict()
        print(f"Firestore Tx Hash Entry: {doc.get('digital_passport_tx_hash')}")
        
    except Exception as e:
        print(f"Failed to process: {e}")

if __name__ == "__main__":
    app = Flask(__name__)
    with app.app_context():
        test_media_factory_integration()
