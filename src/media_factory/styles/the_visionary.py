import ffmpeg
from typing import Any
from src.media_factory.styles.base_style import BaseStyle

class TheVisionary(BaseStyle):
    """
    AI-Guided style that uses ROI tracking for Auto-Reframing.
    Best for: News, Documentaries, Content with clear focus.
    """
    def apply(self, input_stream, text: str, duration: float, roi: Any = None, 
              transcription_data: Any = None, ass_path: Any = None, 
              burst_manifest: Any = None,
              audio_peaks: Any = None, pump_intensity: float = 1.0,
              width: int = 1920, height: int = 1080,
              template: Any = None):
        # 0. Split input for multi-branch usage
        video_split = input_stream.video.split()
        v1 = video_split[0]
        v2 = video_split[1]

        # 1. Background (9:16 blurred)
        bg = self.get_916_background(v1)
        
        # 2. Dynamic Auto-Reframe (The Crop)
        fg = self.apply_roi_framing(v2, roi, iw=width, ih=height)
        
        # 3. Clean Grading
        if template:
            out = self.apply_grading_from_template(fg, template)
        else:
            out = fg.filter('eq', contrast=1.1, brightness=0.02, saturation=1.4)
        
        # 4. Audio-Reactive Pulse
        out = self.apply_audio_pump(out, audio_peaks, intensity=pump_intensity)

        # 5. High-Fidelity Emoji Overlays (Sprite Engine)
        if burst_manifest:
            out = self.apply_emoji_overlays(out, burst_manifest, audio_peaks=audio_peaks)
            
        # 6. Kinetic Typography (ASS) - HEADLINE + CAPTIONS consolidated
        # Applied LAST to ensure text stays on top of emojis
        if ass_path:
            out = self.apply_ass_subtitles(out, ass_path)
        else:
            out = self.apply_kinetic_captions(out, transcription_data)
        
        return self.apply_progress_bar(out, duration)
