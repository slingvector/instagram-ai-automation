import ffmpeg
import logging
import tempfile
import uuid
import os
from google.cloud import storage

from src.config import GCS_BUCKET_RAW, GCS_BUCKET_PROCESSED
from src.ingestion.services.digital_passport_service import DigitalPassportService
from src.media_factory.services.ai_lens import AILens
from src.media_factory.styles.style_factory import StyleFactory
from src.media_factory.styles.template_manager import TemplateManager
from src.media_factory.utils.ass_generator import ASSGenerator
from src.cloud_function.services.vertex_ai_service import VertexAIService

logger = logging.getLogger(__name__)

class VideoProcessorService:
    """
    Ultra-Pro Media Factory: Uses AI-Lens for visual intelligence and 
    StyleFactory for niche-specific cinematic aesthetics.
    """
    def __init__(self, project_id: str,
                 input_bucket_name: str = "",
                 output_bucket_name: str = ""):
        self.project_id = project_id
        self.input_bucket = input_bucket_name or GCS_BUCKET_RAW
        self.output_bucket = output_bucket_name or GCS_BUCKET_PROCESSED
        self.storage_client = storage.Client(project=self.project_id)
        self.ai_lens = AILens(self.project_id)
        self.vertex_ai = VertexAIService(self.project_id)
        self.template_manager = TemplateManager()
        self.ass_generator = ASSGenerator()
        
    def _download_blob(self, gcs_uri: str, local_path: str):
        """Downloads a blob from a 'gs://...' URI to a local path."""
        # gs://bucket_name/path/to/object
        bucket_part = gcs_uri.split("gs://", 1)[1]
        bucket_name = bucket_part.split("/", 1)[0]
        blob_name = bucket_part.split("/", 1)[1]
        
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

    def apply_burn_in(self, raw_video_uri: str, text: str, caption_text: str, job_id: str, niche: str = "general") -> tuple[str, str]:
        """
        Ultra-Pro Pipeline:
        1. AI-Lens Analysis (Visual ROI)
        2. Dynamic Style Selection (Template Factory)
        3. Professional Rendering (FFmpeg Functional)
        4. Web3 Minting
        """
        # Create a temporary directory for the file swap

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, f"input_{job_id}.mp4")
            output_path = os.path.join(tmp_dir, f"output_{job_id}.mp4")
            
            # 1. Download & Analyze
            self._download_blob(raw_video_uri, input_path)
            
            # AI Visual Intelligence: Detect ROI for framing & Word-level Transcription
            analysis = self.ai_lens.analyze_visual_roi(raw_video_uri)
            roi = analysis.get("roi")
            if roi:
                logger.info(f"VideoProcessorService [Job: {job_id}]: Action Zone Trace: {roi}")
            
            # AI Auditory Intelligence: Detect peaks for "pumping" effect
            audio_peaks = self.ai_lens.detect_audio_peaks(input_path)
            
            transcription = self.vertex_ai.transcribe_video_with_timestamps(raw_video_uri)
            
            # 2. Select Style Template
            template_id = self.template_manager.select_template_by_niche(niche)
            template = self.template_manager.get_template(template_id)
            
            # Determine OS-specific font path
            if os.path.exists("/System/Library/Fonts/Helvetica.ttc"):
                font_path = "/System/Library/Fonts/Helvetica.ttc"
            elif os.path.exists("/Library/Fonts/Arial.ttf"):
                font_path = "/Library/Fonts/Arial.ttf"
            else:
                font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
            
            style_template = StyleFactory.get_style(niche, font_path)
            
            # 3. Generate Kinetic Typography (ASS) & Burst Manifest
            ass_path = os.path.join(tmp_dir, f"captions_{job_id}.ass")
            _, burst_manifest = self.ass_generator.generate(transcription, ass_path, template=template, headline=text)

            # 4. Apply Multi-Pass Rendering
            logger.info(f"Ultra-Pro v2: Applying {style_template.__class__.__name__} with '{template_id}' template...")
            try:
                input_stream = ffmpeg.input(input_path)
                
                # Get video duration and resolution for aspect-aware framing
                probe = ffmpeg.probe(input_path)
                duration = float(probe['format']['duration'])
                video_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
                width = int(video_stream['width']) if video_stream else 1920
                height = int(video_stream['height']) if video_stream else 1080
                
                # Apply Style with ROI, Transcription, ASS path, Burst Manifest, Audio Peaks, Input Dimensions and Template
                video_out = style_template.apply(
                    input_stream, text, duration, 
                    roi=roi, 
                    transcription_data=transcription, 
                    ass_path=ass_path, 
                    burst_manifest=burst_manifest,
                    audio_peaks=audio_peaks,
                    pump_intensity=template.get("pump_intensity", 1.0),
                    width=width,
                    height=height,
                    template=template
                )

                # Robust stream mapping: check if audio exists
                has_audio = any(s['codec_type'] == 'audio' for s in probe['streams'])
                
                output_args = {}
                if has_audio:
                    output_args = {"acodec": "aac"}
                    output_stream = ffmpeg.output(video_out, input_stream.audio, output_path, vcodec="libx264", crf=23, preset="veryfast", **output_args)
                else:
                    output_stream = ffmpeg.output(video_out, output_path, vcodec="libx264", crf=23, preset="veryfast")
                
                (
                    output_stream
                    .overwrite_output()
                    .global_args('-nostdin')
                    .run(capture_stdout=True, capture_stderr=True)
                )
            except ffmpeg.Error as e:
                logger.error(f"FFmpeg Ultra-Pro failed: {e.stderr.decode('utf8')}")
                raise Exception(f"Visual processing failed for job {job_id}")

            # 3. Generate Digital Passport (Immutable Web3 Hash)
            logger.info(f"Generating Digital Passport for {output_path}...")
            passport_service = DigitalPassportService()
            tx_receipt = passport_service.generate_and_mint_passport(output_path, caption_text)
            
            # 4. Upload the encoded video
            output_blob_name = f"processed_{job_id}.mp4"
            processed_gcs_uri = self._upload_blob(output_path, output_blob_name)
            
            return processed_gcs_uri, tx_receipt
