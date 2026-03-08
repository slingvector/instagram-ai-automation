import os
import uuid
import logging
import subprocess
import tempfile
from pathlib import Path
from google.cloud import storage

logger = logging.getLogger(__name__)

class GCSUploaderService:
    """
    Downloads an Instagram Reel video using yt-dlp and uploads it to GCS.
    Returns the gs:// URI of the uploaded file.
    """

    def __init__(self, bucket_name: str, credentials_path: str = None):
        self.bucket_name = bucket_name
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        self.client = storage.Client()
        self.bucket = self.client.bucket(self.bucket_name)

    def download_and_upload(self, reel_url: str) -> tuple[str, float]:
        """
        Downloads a Reel and uploads it to GCS.
        Returns a tuple: (GCS URI, duration_in_seconds).
        Raises an exception if download or upload fails.
        """
        job_id = str(uuid.uuid4())[:8]
        filename = f"reel_{job_id}.mp4"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, filename)

            logger.info(f"Downloading Reel from {reel_url} ...")
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--quiet",
                    "--no-warnings",
                    "-f", "best[height<=1080]", # Forcing smaller files
                    "-o", output_path,
                    reel_url,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.error(f"yt-dlp failed: {result.stderr}")
                raise RuntimeError(f"yt-dlp download failed: {result.stderr}")

            if not os.path.exists(output_path):
                # yt-dlp may have added an extension — find the file
                found = list(Path(tmpdir).glob("reel_*"))
                if not found:
                    raise RuntimeError("yt-dlp produced no output file.")
                output_path = str(found[0])
                filename = Path(output_path).name

            # Auto-Trim long videos to 60 seconds
            import json
            duration = 0.0
            probe_result = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", output_path
            ], capture_output=True, text=True)
            
            try:
                duration = float(probe_result.stdout.strip())
                if duration > 180: # 3 minutes
                    logger.info(f"Video duration ({duration}s) exceeds 3 mins. Trimming to first 60s...")
                    trimmed_path = os.path.join(tmpdir, f"trimmed_{filename}")
                    trim_result = subprocess.run([
                        "ffmpeg", "-y", "-i", output_path,
                        "-t", "60", "-c", "copy", trimmed_path
                    ], capture_output=True, text=True)
                    if trim_result.returncode == 0 and os.path.exists(trimmed_path):
                        output_path = trimmed_path
                        filename = f"trimmed_{filename}"
                        duration = 60.0
                    else:
                        logger.warning(f"FFmpeg trim failed. Uploading raw video. {trim_result.stderr}")
            except Exception as e:
                logger.warning(f"Failed to probe duration or trim: {e}")

            logger.info(f"Uploading {filename} to GCS bucket {self.bucket_name} ...")
            blob = self.bucket.blob(f"reels/{filename}")
            blob.upload_from_filename(output_path, content_type="video/mp4")

            gcs_uri = f"gs://{self.bucket_name}/reels/{filename}"
            logger.info(f"Upload complete: {gcs_uri}")
            return gcs_uri, duration

