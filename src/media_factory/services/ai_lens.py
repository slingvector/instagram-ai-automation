import logging
import json
import subprocess
import re
from src.cloud_function.services.vertex_ai_service import VertexAIService

logger = logging.getLogger(__name__)

class AILens:
    """
    The 'Eye' of the Media Factory. Performs visual and auditory scene analysis.
    """
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.ai_service = VertexAIService(project_id)

    def analyze_visual_roi(self, video_uri: str) -> dict:
        """
        Uses Gemini 2.0 to detect the Primary Subject/ROI in the video.
        Returns normalized coordinates [ymin, xmin, ymax, xmax] for auto-reframing.
        """
        prompt = """
        Analyze this video clip. 
        Identify the 'Action Zone' (Safe ROI) that encompasses the primary subject AND their range of movement throughout the clip.
        For sports (like badminton, tennis, cricket), ensure the box is wide enough to catch the athlete even when they move laterally.
        Return a single bounding box that represents the 'Safe Action Zone' for the entire clip.
        Format response as JSON: {"roi": {"ymin": 0, "xmin": 0, "ymax": 1000, "xmax": 1000}, "tracking_notes": "centering on athlete movement zone"}
        """
        logger.info(f"AI-Lens: Analyzing visual ROI for {video_uri}...")
        try:
            return self.ai_service.analyze_video_roi(video_uri)
        except Exception as e:
            logger.error(f"AI-Lens visual analysis failed: {e}")
            return {"roi": {"ymin": 0, "xmin": 0, "ymax": 1000, "xmax": 1000}, "error": str(e)}

    def detect_audio_peaks(self, local_path: str) -> list[float]:
        """
        Uses FFmpeg's astats/ebur128 to detect volume peaks (beats).
        Returns a list of timestamps (seconds) where peaks occur.
        """
        logger.info(f"AI-Lens: Detecting audio peaks in {local_path}...")
        try:
            # Use astats to find max volumes in chunks
            # We use a 100ms window to detect peaks
            cmd = [
                "ffmpeg", "-i", local_path,
                "-af", "aselect='gt(volume,0.5)',astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.Peak_level",
                "-f", "null", "-"
            ]
            # Improved peak detection: astats gives us local peaks.
            # For a more robust "beat" detection, we look for relative spikes.
            # Simplified approach: use silent/noise detection to find transients
            cmd_transients = [
                "ffmpeg", "-i", local_path,
                "-af", "silencedetect=n=-30dB:d=0.1",
                "-f", "null", "-"
            ]
            
            result = subprocess.run(cmd_transients, capture_output=True, text=True)
            output = result.stderr
            
            # Parse silence_end timestamps as peak/start of a "beat"
            peaks = []
            for line in output.splitlines():
                if "silence_end" in line:
                    match = re.search(r"silence_end: ([\d\.]+)", line)
                    if match:
                        peaks.append(float(match.group(1)))
            
            # If no silence detected (constant loud noise), fallback to periodic pulses
            if not peaks:
                logger.warning("AI-Lens: No transient peaks detected. Using periodic fallback.")
                return [i * 2.0 for i in range(10)]
                
            logger.info(f"AI-Lens: Detected {len(peaks)} audio peaks.")
            return sorted(list(set(peaks))) # Unique timestamps
        except Exception as e:
            logger.error(f"AI-Lens audio analysis failed: {e}")
            return []
