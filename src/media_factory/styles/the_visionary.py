import ffmpeg
from .base_style import BaseStyle

class TheVisionary(BaseStyle):
    """
    AI-Guided style that uses ROI tracking for Auto-Reframing.
    Best for: News, Documentaries, Content with clear focus.
    """
    def apply(self, input_stream, text: str, duration: float, roi: dict = None, 
              transcription_data: dict = None, ass_path: str = None, 
              audio_peaks: list = None, pump_intensity: float = 1.0,
              width: int = 1920, height: int = 1080,
              template: dict = None):
        # 1. Background (9:16 blurred)
        bg = self.get_916_background(input_stream.video)
        
        # 2. Dynamic Auto-Reframe (The Crop)
        fg = self.apply_roi_framing(input_stream.video, roi, iw=width, ih=height)
        
        # 3. Clean Grading
        if template:
            out = self.apply_grading_from_template(fg, template)
        else:
            out = fg.filter('eq', contrast=1.1, brightness=0.02, saturation=1.4)
        
        # 4. Audio-Reactive Pulse
        out = self.apply_audio_pump(out, audio_peaks, intensity=pump_intensity)

        # 5. Kinetic Typography (ASS) - HEADLINE + CAPTIONS consolidated
        if ass_path:
            out = self.apply_ass_subtitles(out, ass_path)
        else:
            out = self.apply_kinetic_captions(out, transcription_data)
        
        return self.apply_progress_bar(out, duration)
