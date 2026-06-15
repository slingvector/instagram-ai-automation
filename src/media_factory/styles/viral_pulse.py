import ffmpeg
from typing import Any
from src.media_factory.styles.base_style import BaseStyle

class ViralPulse(BaseStyle):
    """
    High-energy style with hyper-saturation, neon tints, and loud typography.
    Best for: Sports, Tech News, Stocks.
    """
    def apply(self, input_stream, text: str, duration: float, roi: Any = None, 
              transcription_data: Any = None, ass_path: Any = None, 
              burst_manifest: Any = None,
              audio_peaks: Any = None, pump_intensity: float = 1.0,
              width: int = 1920, height: int = 1080,
              template: Any = None):
        # 0. Split input for multi-branch usage
        split = input_stream.video.split()
        v1 = split.stream(0)
        v2 = split.stream(1)

        # 1. Background (9:16 blurred)
        bg = self.get_916_background(v1)
        
        # 2. Viral Grading (Hyper-saturation or Template-driven)
        if template:
            graded = self.apply_grading_from_template(v2, template)
        else:
            graded = self.apply_viral_grading(v2)
        
        # 3. Dynamic ROI Framing
        framed = self.apply_roi_framing(graded, roi, iw=width, ih=height)
        
        # 4. Composite
        out = ffmpeg.overlay(bg, framed, x='(W-w)/2', y='(H-h)/2')
        
        # 5. Audio-Reactive "Pump" (Novelty signal)
        out = self.apply_audio_pump(out, audio_peaks, intensity=pump_intensity)

        # 6. High-Fidelity Emoji Overlays (Sprite Engine)
        if burst_manifest:
            out = self.apply_emoji_overlays(out, burst_manifest, audio_peaks=audio_peaks)
            
        # 7. Kinetic Typography (ASS) - HEADLINE + CAPTIONS consolidated
        # Applied LAST to ensure text stays on top of emojis
        if ass_path:
            out = self.apply_ass_subtitles(out, ass_path)
        else:
            out = self.apply_kinetic_captions(out, transcription_data)
        
        # 8. Neon Progress Bar (Cyan)
        # Use primary color from template if available
        pb_color = '0x00FFFF@0.9'
        if template and "color_scheme" in template:
            pb_color = template["color_scheme"].get("primary", "cyan")
            if pb_color == "white": pb_color = "0xFFFFFF@0.9"
            if pb_color == "magenta": pb_color = "0xFF00FF@0.9"
            if pb_color.startswith("#"): pb_color = pb_color.replace("#", "0x") + "@0.9"

        return self.apply_progress_bar(out, duration).filter('drawbox', x=0, y='ih-10', w=f'iw*t/{duration}', h=10, color=pb_color, t='fill')
