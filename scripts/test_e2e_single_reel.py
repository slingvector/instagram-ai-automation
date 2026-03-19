import os
import sys
import logging
import uuid
from pathlib import Path
from google.cloud import firestore

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.scraper.services.gcs_uploader_service import GCSUploaderService
from src.media_factory.services.video_processor_service import VideoProcessorService
from src.media_factory.repositories.processed_job_repository import ProcessedJobRepository

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("e2e_tester")

# Constants
TEST_REEL_URL = "https://www.instagram.com/reel/DE-T87eP_pD/"
LOCAL_VIDEO_PATH = "The Full Dustin and Suzie NeverEnding Story Scene ｜ Stranger Things S3 [O5HQ1sZseKg].mp4"
GCP_PROJECT_ID = "mcr-relay-1772228380"
KEY_PATH = "modernos-edge-agent-key.json"

def run_e2e():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH
    job_id = f"e2e_{uuid.uuid4().hex[:8]}"
    
    print(f"\n{'='*60}")
    print(f"🚀 STARTING E2E REEL SIMULATION [Job: {job_id}]")
    print(f"{'='*60}")

    try:
        # Set FontConfig for Mac local dev
        os.environ["FONTCONFIG_FILE"] = "/tmp/fonts.conf"
        
        # 1. Ingestion Phase: Download & Upload to GCS
        print(f"\n📦 STAGE 1: INGESTION (Scrape & Download)")
        # ... (Stage 1 logic remains same)
        scraper = GCSUploaderService(bucket_name=f"{GCP_PROJECT_ID}-raw-input")
        
        try:
            print(f"Attempting to download: {TEST_REEL_URL}")
            gcs_raw_uri, duration = scraper.download_and_upload(TEST_REEL_URL)
        except Exception as e:
            print(f"⚠️ Download failed ({e}). Falling back to local file: {LOCAL_VIDEO_PATH}")
            if not os.path.exists(LOCAL_VIDEO_PATH):
                raise RuntimeError(f"Fallback file not found: {LOCAL_VIDEO_PATH}")
            gcs_raw_uri = scraper.upload_file(LOCAL_VIDEO_PATH)
            duration = 60.0
            
        print(f"✅ Raw Video Ready: {gcs_raw_uri} (Duration: {duration}s)")

        # 2. Setup Firestore Mock Job
        # ... (Stage 2 logic remains same)
        print(f"\n🔥 STAGE 2: FIRESTORE SETUP")
        db = firestore.Client.from_service_account_json(KEY_PATH, project=GCP_PROJECT_ID)
        job_ref = db.collection("job_queue").document(job_id)
        job_ref.set({
            "status": "INGESTED",
            "gcs_raw_video_uri": gcs_raw_uri,
            "ai_metadata": {
                "burn_in_text": "EMOJI BURST TEST 🚀",
                "caption": "Testing the new emoji-burst logic in the E2E flow! #automation #mcr",
                "hashtags": ["automation", "mcr", "test"]
            },
            "created_at": firestore.SERVER_TIMESTAMP
        })
        print(f"✅ Mock job {job_id} created in Firestore.")

        # 3. Media Factory Phase
        print(f"\n🎬 STAGE 3: MEDIA FACTORY (AI Lens + Rendering)")
        video_service = VideoProcessorService(project_id=GCP_PROJECT_ID)
        
        # MOCK TRANSCRIPTION
        mock_transcription = {
            "words": [
                {"word": "MCR", "start": 0.5, "end": 1.0},
                {"word": "EMOJI", "start": 2.0, "end": 2.5},
                {"word": "BURST", "start": 3.5, "end": 4.0},
                {"word": "TEST!", "start": 5.0, "end": 5.5}
            ],
            "sentiment_clusters": [
                {"start": 0.5, "end": 1.5, "intensity": 0.9, "reaction_pool": "🔥🚀💎", "burst_count": 8, "text_emojis": "🔥"},
                {"start": 2.0, "end": 3.0, "intensity": 0.85, "reaction_pool": "✨💫❤", "burst_count": 5, "text_emojis": "✨"},
                {"start": 3.5, "end": 4.5, "intensity": 0.95, "reaction_pool": "💯💥🙌", "burst_count": 10, "text_emojis": "💯"},
                {"start": 5.0, "end": 6.5, "intensity": 0.9, "reaction_pool": "🎊🎉🎈", "burst_count": 8, "text_emojis": "🎊"}
            ],
            "duration": 60.0
        }
        
        from unittest.mock import MagicMock
        video_service.vertex_ai.transcribe_video_with_timestamps = MagicMock(return_value=mock_transcription)
        
        try:
            processed_uri, tx_receipt = video_service.apply_burn_in(
                raw_video_uri=gcs_raw_uri,
                text="EMOJI BURST TEST 🚀",
                caption_text="Testing the new emoji-burst logic!",
                job_id=job_id,
                niche="general"
            )
            print(f"✅ Media Processed! Final URI: {processed_uri}")
        except Exception as e:
            print(f"❌ Media Factory Failed: {e}")
            raise

        # 4. Final Status Update
        # ... 

        # 4. Final Status Update
        print(f"\n🔥 STAGE 4: UPDATING FIRESTORE")
        firestore_repo = ProcessedJobRepository(project_id=GCP_PROJECT_ID)
        firestore_repo.mark_job_completed(job_id, processed_uri, tx_receipt)
        print(f"✅ Job {job_id} marked as READY_FOR_PUBLISHING.")

        # 5. Summary
        print(f"\n🏁 STAGE 5: FINAL VERIFICATION")
        final_job = job_ref.get().to_dict()
        print(f"Final Job Status: {final_job.get('status')}")
        print(f"Processed Video:  {final_job.get('gcs_processed_video_uri')}")

        print(f"\n{'='*60}")
        print(f"🎉 E2E SIMULATION SUCCESS!")
        print(f"Processed file is ready for visual sign-off.")
        print(f"{'='*60}")
        
    except Exception as e:
        logger.error(f"❌ E2E FLOW FAILED: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run_e2e()
