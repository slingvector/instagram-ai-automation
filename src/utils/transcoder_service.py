import logging
import time
from typing import Optional
from google.cloud.video import transcoder_v1
from google.cloud.video.transcoder_v1.services.transcoder_service import TranscoderServiceClient

logger = logging.getLogger(__name__)

class HlsTranscoderService:
    def __init__(self, project_id: str, location: str = "us-central1", cdn_host: Optional[str] = None):
        self.project_id = project_id
        self.location = location
        self.cdn_host = cdn_host
        try:
            self.client = TranscoderServiceClient()
        except Exception as e:
            logger.warning(f"Could not initialize TranscoderServiceClient: {e}")
            self.client = None

    def _hls_job_config(self) -> transcoder_v1.types.JobConfig:
        """Single 720p rendition HLS with ~4s segments."""
        return transcoder_v1.types.JobConfig(
            elementary_streams=[
                transcoder_v1.types.ElementaryStream(
                    key="video-stream0",
                    video_stream=transcoder_v1.types.VideoStream(
                        h264=transcoder_v1.types.VideoStream.H264CodecSettings(
                            height_pixels=720, width_pixels=1280,
                            bitrate_bps=3_000_000, frame_rate=30,
                        ),
                    ),
                ),
                transcoder_v1.types.ElementaryStream(
                    key="audio-stream0",
                    audio_stream=transcoder_v1.types.AudioStream(
                        codec="aac", bitrate_bps=128_000,
                    ),
                ),
            ],
            mux_streams=[
                transcoder_v1.types.MuxStream(
                    key="media-ts",
                    container="ts",
                    elementary_streams=["video-stream0", "audio-stream0"],
                    segment_settings=transcoder_v1.types.SegmentSettings(
                        segment_duration={"seconds": 4},
                    ),
                ),
            ],
            manifests=[
                transcoder_v1.types.Manifest(
                    file_name="render.m3u8",
                    type_=transcoder_v1.types.Manifest.ManifestType.HLS,
                    mux_streams=["media-ts"],
                ),
            ],
        )

    def submit_and_wait(self, input_uri: str, output_uri: str, poll_secs: int = 5, timeout_secs: int = 1800) -> Optional[str]:
        """
        Submits a transcoder job and waits for completion.
        Returns the CDN URL to the manifest if successful and cdn_host is set.
        """
        if not self.client:
            logger.error("TranscoderServiceClient is not initialized.")
            return None

        if not output_uri.endswith("/"):
            output_uri += "/"

        parent = f"projects/{self.project_id}/locations/{self.location}"
        job = transcoder_v1.types.Job(
            input_uri=input_uri,
            output_uri=output_uri,
            config=self._hls_job_config(),
        )
        
        try:
            created = self.client.create_job(parent=parent, job=job)
            logger.info(f"[transcoder] submitted {created.name}")
        except Exception as e:
            logger.error(f"[transcoder] Failed to submit job: {e}")
            return None

        deadline = time.time() + timeout_secs
        while time.time() < deadline:
            try:
                cur = self.client.get_job(name=created.name)
                state = cur.state.name
                if state == "SUCCEEDED":
                    logger.info("[transcoder] SUCCEEDED")
                    
                    if self.cdn_host:
                        path = output_uri.split("/", 3)[3] if output_uri.count("/") >= 3 else ""
                        manifest_url = f"{self.cdn_host.rstrip('/')}/{path}render.m3u8"
                        return manifest_url
                    return output_uri + "render.m3u8"
                    
                if state == "FAILED":
                    logger.error(f"[transcoder] FAILED: {cur.error}")
                    return None
            except Exception as e:
                logger.warning(f"[transcoder] Status check failed: {e}")
                
            time.sleep(poll_secs)
            
        logger.error("[transcoder] timed out waiting for job.")
        return None
