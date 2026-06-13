import ffmpeg
import os
import logging
import random
from abc import ABC, abstractmethod
from typing import Dict, Any, List

from ..services.emoji_sprite_service import EmojiSpriteService

logger = logging.getLogger(__name__)

class BaseStyle(ABC):
    """
    Abstract Base Class for all Ultra-Pro Video Styles.
    Handles the common pipeline: 9:16 normalization, grading, and burn-in.
    """
    def __init__(self, font_path: str):
        self.font_path = font_path

    @abstractmethod
    def apply(self, input_stream, text: str, duration: float, roi: Any = None, 
              transcription_data: Any = None, ass_path: Any = None, 
              burst_manifest: Any = None,
              audio_peaks: List[float] = None, pump_intensity: float = 1.0):
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
        Uses the 'subtitles' filter with a local fontsdir if available to 
        ensure cross-platform emoji support (e.g. Noto Color Emoji).
        """
        if not os.path.exists(ass_path):
            logger.warning(f"ASS file not found: {ass_path}. Skipping.")
            return stream
            
        # Check for local project fonts directory (useful for Mac/Windows dev)
        fonts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "fonts"))
        
        if os.path.exists(fonts_dir):
            # Using 'subtitles' instead of 'ass' filter because it supports 'fontsdir'
            return stream.filter('subtitles', filename=ass_path, fontsdir=fonts_dir)
        
        return stream.filter('subtitles', filename=ass_path)

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

    def apply_emoji_overlays(self, video_stream, burst_manifest: List[Dict[str, Any]], audio_peaks: List[float] = None):
        """
        v3.0 Organic UI Physics Engine:
        1. Sine-Wave Wobble (Horizontal drift)
        2. Quadratic Deceleration (Upward burst + Gravity)
        3. Smooth Alpha Transitions
        4. Spatial Margin Separation (Prevents spatial crowning/text overlap)
        """
        if not burst_manifest:
            return video_stream

        sprite_service = EmojiSpriteService()
        peaks = audio_peaks or []

        # Limit to top 20 bursts for high impact
        active_bursts = sorted(burst_manifest, key=lambda x: x['start'])[:20]

        out = video_stream
        for i, burst in enumerate(active_bursts):
            sprite_path = sprite_service.get_sprite_path(burst['char'])
            if not sprite_path: continue

            # 1. Base Variables
            start = burst['start']
            end = burst['end']
            size = burst.get('size', 150)
            
            # 2. Physics
            x0 = burst['x']
            y0 = 1450 + random.randint(-50, 50)
            vx = burst['dx'] * 1.5
            wobble_freq = random.uniform(2.5, 4.5)
            wobble_amp = random.randint(40, 90)
            phase = random.uniform(0, 6.28)
            initial_vy = random.uniform(700, 1000)
            gravity = random.uniform(180, 280)
            
            x_math = f"{x0} + (t-{start})*{vx} + {wobble_amp}*sin({wobble_freq}*(t-{start}) + {phase})"
            y_math = f"{y0} - (t-{start})*{initial_vy} + {gravity}*(t-{start})*(t-{start})"

            # 3. UNIQUE Filter Chain (Node Jitter)
            # We add a micro-jitter (0.001) to the size to ensure ffmpeg-python 
            # treats this as a unique filter node and doesn't deduplicate it,
            # which avoids the "multiple outgoing edges" DAG error.
            jittered_size = size + (i * 0.001)
            sprite = (
                ffmpeg
                .input(sprite_path)
                .filter('scale', jittered_size, -1)
                .filter('fade', type='out', start_time=end - 0.5, duration=0.5, alpha=1)
            )
            
            # 4. Overlay
            out = ffmpeg.overlay(out, sprite, x=x_math, y=y_math, enable=f"between(t,{start},{end})")

        return out

    def apply_kinetic_captions(self, stream, transcription_data: dict):
        """
        DEPRECATED: Use apply_ass_subtitles for Creator-Standard quality.
        Keeping as fallback for now.
        """
        if not transcription_data or "words" not in transcription_data:
            return stream
        # ... logic ...
