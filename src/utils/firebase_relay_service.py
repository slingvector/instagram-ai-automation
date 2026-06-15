import datetime as dt
import logging
import os
import subprocess
import firebase_admin
from firebase_admin import credentials, storage
from typing import Optional

logger = logging.getLogger(__name__)

class FirebaseRelayService:
    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        
        if not firebase_admin._apps:
            try:
                cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                cred = credentials.Certificate(cred_path) if cred_path else credentials.ApplicationDefault()
                firebase_admin.initialize_app(cred, {"storageBucket": self.bucket_name})
                logger.info(f"Firebase Admin initialized for bucket: {self.bucket_name}")
            except Exception as e:
                logger.error(f"Failed to initialize Firebase Admin: {e}")

    def apply_faststart(self, input_path: str) -> Optional[str]:
        """Runs ffmpeg to move the moov atom to the front for instant playback."""
        if not os.path.exists(input_path):
            logger.error(f"Input file not found: {input_path}")
            return None
            
        out_path = input_path.replace(".mp4", "_faststart.mp4")
        
        try:
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", "-movflags", "+faststart", out_path]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                logger.error(f"ffmpeg faststart failed: {result.stderr}")
                return None
                
            return out_path
        except Exception as e:
            logger.error(f"Error running ffmpeg: {e}")
            return None

    def upload_to_firebase(self, path: str, dest: Optional[str] = None, ttl_days: int = 7) -> Optional[str]:
        """Uploads a video to Firebase Storage and returns a signed download URL."""
        if not os.path.isfile(path):
            logger.error(f"Not a file: {path}")
            return None
            
        try:
            bucket = storage.bucket()
            dest = dest or f"previews/{dt.date.today():%Y-%m-%d}/{os.path.basename(path)}"
            blob = bucket.blob(dest)
            blob.content_type = "video/mp4"
            blob.cache_control = "public, max-age=86400"
            
            logger.info(f"Uploading {path} to Firebase Storage as {dest}...")
            blob.upload_from_filename(path)

            url = blob.generate_signed_url(
                version="v4",
                expiration=dt.timedelta(days=ttl_days),
                method="GET",
            )
            logger.info(f"Firebase upload complete. Generated URL.")
            return url
        except Exception as e:
            logger.error(f"Failed to upload to Firebase: {e}")
            return None

    def relay_video(self, input_path: str) -> Optional[str]:
        """Full pipeline: applies faststart and uploads to Firebase."""
        faststart_path = self.apply_faststart(input_path)
        if not faststart_path:
            return None
            
        url = self.upload_to_firebase(faststart_path)
        
        # Cleanup temporary faststart file
        if os.path.exists(faststart_path) and faststart_path != input_path:
            os.remove(faststart_path)
            
        return url
