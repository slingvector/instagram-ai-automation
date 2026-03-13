import ffmpeg
import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any

logger = logging.getLogger(__name__)

class BaseStyle(ABC):
    """
    Abstract Base Class for all Ultra-Pro Video Styles.
    Handles the common pipeline: 9:16 normalization, grading, and burn-in.
    """
    def __init__(self, font_path: str):
        self.font_path = font_path

    @abstractmethod
    def apply(self, input_stream, text: str, duration: float, roi: dict = None, 
              transcription_data: dict = None, ass_path: str = None, 
              audio_peaks: list = None, pump_intensity: float = 1.0):
        """
        Applies the style-specific filter graph to the input stream.
        """
        pass

    def get_916_background(self, stream):
        """Common 9:16 blurred background logic."""
        return (
            stream
            .filter('scale', 1080, 1920, force_original_aspect_ratio='increase')
            .filter('crop', 1080, 1920)
            .filter('boxblur', 25, 20)
        )

    def apply_standard_grading(self, stream):
        """Cinematic pop: Saturation + Contrast."""
        return stream.filter('eq', contrast=1.2, brightness=0.02, saturation=1.5)

    def apply_progress_bar(self, stream, duration: float):
        """Industrial green progress bar at the bottom."""
        # Use numeric duration to avoid 'Undefined constant' error in FFmpeg eval
        return stream.filter('drawbox', x=0, y='ih-8', w=f'iw*t/{duration}', h=8, color='0x00FF00@0.8', t='fill')

    def apply_viral_grading(self, stream):
        """High-energy pop: Extreme Saturation + Contrast for viral look."""
        return stream.filter('eq', contrast=1.3, brightness=0.03, saturation=1.8)

    def apply_grading_from_template(self, stream, template: Dict[str, Any]):
        """
        Applies precise color grading (contrast, saturation, brightness, tints)
        configured in templates.yaml.
        """
        if not template or "grading" not in template:
            return self.apply_standard_grading(stream)
            
        params = template["grading"]
        contrast = params.get("contrast", 1.2)
        saturation = params.get("saturation", 1.5)
        brightness = params.get("brightness", 0.02)
        
        # Apply standard eq filter
        out = stream.filter('eq', contrast=contrast, brightness=brightness, saturation=saturation)
        
        # Apply color tints if defined (e.g., blue-grey for geopolitical)
        tint = params.get("color_tint")
        if tint == "blue-grey":
            out = out.filter('colorbalance', rs=0.05, bs=0.1, rm=0.05, bm=0.1)
        elif tint == "gold":
             out = out.filter('colorbalance', rs=0.1, gs=0.05, bs=-0.1)
        
        # Apply sharpness if requested
        if params.get("sharpness"):
            out = out.filter('unsharp', luma_msize_x=3, luma_msize_y=3, luma_amount=params["sharpness"])
            
        return out

    def apply_roi_framing(self, stream, roi: dict, iw: int = 1920, ih: int = 1080):
        """
        Dynamically reframes (crops) the video based on the AI-detected Action Zone.
        Ensures the crop window contains the primary movement range.
        If the video is already vertical, it skips aggressive cropping.
        """
        if not roi or not all(k in roi for k in ['ymin', 'xmin', 'ymax', 'xmax']):
             # Fallback to center-weighted vertical slice
             roi = {"ymin": 0, "xmin": 250, "ymax": 1000, "xmax": 750}
        
        # Check aspect ratio: if vertical (~9:16), just scale and centered-crop gently
        aspect_ratio = iw / ih
        if aspect_ratio < 0.7: # Approx 9:16
            logger.info(f"BaseStyle: Detected Vertical Input ({iw}x{ih}). Skipping aggressive ROI crop.")
            return (
                stream
                .filter('scale', 1080, 1920, force_original_aspect_ratio='increase')
                .filter('crop', 1080, 1920)
            )

        # Landscape logic: Calculate the Action Zone center
        x_min_px = roi.get('xmin', 250) / 1000 * iw
        x_max_px = roi.get('xmax', 750) / 1000 * iw
        x_center = (x_min_px + x_max_px) / 2
        
        # Crop width for 9:16 aspect
        crop_w = int(ih * (9/16)) # ~607px
        crop_h = ih
        
        # If the Action Zone is wider than our crop, we prioritize the center of the zone
        crop_x = int(max(0, min(iw - crop_w, x_center - (crop_w/2))))
        
        logger.info(f"BaseStyle: Reframing Action Zone at x={crop_x}, width={crop_w} for {iw}x{ih} input.")
        
        return (
            stream
            .filter('crop', crop_w, crop_h, crop_x, 0)
            .filter('scale', 1080, 1920)
        )

    def apply_ass_subtitles(self, stream, ass_path: str):
        """
        Renders high-performance kinetic typography using the .ass file.
        """
        if not os.path.exists(ass_path):
            logger.warning(f"ASS file not found: {ass_path}. Skipping.")
            return stream
            
        return stream.filter('ass', filename=ass_path)

    def apply_audio_pump(self, stream, peaks: list[float], intensity: float = 1.0):
        """
        Creates a 'Scale Pump' effect on audio peaks (beats).
        The video subtly zooms in and out on every beat.
        """
        if not peaks:
            return stream

        # Limit to top peaks to avoid excessive expression length
        peaks = sorted(peaks)[:20]

        # Construct a complex scale expression based on peaks
        # zoom = 1.0 + (0.05 * intensity) * sum(exp(-25*(time-p)^2))
        magnitude = 0.05 * intensity
        expr = "1.0"
        for p in peaks:
            # Multi-scale pulses using gaussian-like windows
            expr += f" + {magnitude}*exp(-25*(time-{p})*(time-{p}))"
            
        return stream.filter('zoompan', z=expr, x='iw/2-(iw/zoom/2)', y='ih/2-(ih/zoom/2)', d=1, s='1080x1920', fps=30)

    def apply_kinetic_captions(self, stream, transcription_data: dict):
        """
        DEPRECATED: Use apply_ass_subtitles for Creator-Standard quality.
        Keeping as fallback for now.
        """
        if not transcription_data or "words" not in transcription_data:
            return stream
        # ... logic ...
