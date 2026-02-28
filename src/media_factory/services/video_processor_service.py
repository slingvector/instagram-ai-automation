import ffmpeg
import logging
import tempfile
import uuid
import os
from google.cloud import storage

logger = logging.getLogger(__name__)

class VideoProcessorService:
    """
    Downloads raw video from GCS, overlays stylish text using ffmpeg-python,
    and uploads the finished video back to the processed GCS bucket.
    """
    def __init__(self, project_id: str,
                 input_bucket_name: str = "mcr-relay-1772228380-raw-input",
                 output_bucket_name: str = "mcr-relay-1772228380-processed-output"):
        self.project_id = project_id
        self.input_bucket = input_bucket_name
        self.output_bucket = output_bucket_name
        self.storage_client = storage.Client(project=self.project_id)
        
    def _download_blob(self, gcs_uri: str, local_path: str):
        """Downloads a blob from a 'gs://...' URI to a local path."""
        # gs://bucket_name/path/to/object
        bucket_part = gcs_uri.split("gs://")[1]
        bucket_name = bucket_part.split("/")[0]
        blob_name = "/".join(bucket_part.split("/")[1:])
        
        bucket = self.storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(local_path)
        logger.info(f"Downloaded {gcs_uri} to {local_path}")

    def _upload_blob(self, local_path: str, destination_blob_name: str) -> str:
        """Uploads a file to the configured output bucket."""
        bucket = self.storage_client.bucket(self.output_bucket)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(local_path, content_type="video/mp4")
        gcs_uri = f"gs://{self.output_bucket}/{destination_blob_name}"
        logger.info(f"Uploaded {local_path} to {gcs_uri}")
        return gcs_uri

    def apply_burn_in(self, raw_video_uri: str, text: str, job_id: str) -> str:
        """
        Executes FFmpeg with a drawtext filter to place text.
        """
        # Create a temporary directory for the file swap
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, f"input_{job_id}.mp4")
            output_path = os.path.join(tmp_dir, f"output_{job_id}.mp4")
            
            # 1. Download the raw video
            self._download_blob(raw_video_uri, input_path)
            
            # 2. Process with FFmpeg
            logger.info(f"Burning text '{text}' onto video with FFmpeg...")
            
            # The 'drawtext' filter settings
            # We use a built-in font or the installed 'LiberationSans-Bold' from apt
            # X/Y: centered near the top third (x=(w-text_w)/2:y=(h-text_h)/4)
            # Box: semi-transparent black background behind the white text for readability
            text_filter = (
                f"drawtext=fontfile=/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf:"
                f"text='{text}':"
                f"fontcolor=white:"
                f"fontsize=w/10:" 
                f"box=1:boxcolor=black@0.6:boxborderw=10:"
                f"x=(w-text_w)/2:y=(h-text_h)/4"
            )
            
            try:
                (
                    ffmpeg
                    .input(input_path)
                    .output(output_path, vf=text_filter, acodec="copy", vcodec="libx264")
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            except ffmpeg.Error as e:
                logger.error(f"FFmpeg process failed: {e.stderr.decode('utf8')}")
                raise Exception(f"Video processing failed for job {job_id}")

            # 3. Upload the encoded video
            output_blob_name = f"processed_{job_id}.mp4"
            processed_gcs_uri = self._upload_blob(output_path, output_blob_name)
            
            return processed_gcs_uri
