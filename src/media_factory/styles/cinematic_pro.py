import ffmpeg
from .base_style import BaseStyle

class CinematicPro(BaseStyle):
    """
    High-end cinematic style with heavy grading, letterboxing, and Ken Burns motion.
    Best for: Travel, Storytelling.
    """
    def apply(self, input_stream, text: str, duration: float, roi: dict = None, 
              transcription_data: dict = None, ass_path: str = None, 
              audio_peaks: list = None, pump_intensity: float = 1.0,
              width: int = 1920, height: int = 1080,
              template: dict = None):
        # 1. Background (9:16 blurred)
        bg = self.get_916_background(input_stream.video)
        
        # 2. Foreground with Ken Burns zoom (slow 1.1x zoom over time)
        fg = (
            input_stream.video
            .filter('scale', 1080, -1)
            # Subtle slow zoom
            .filter('zoompan', z='min(zoom+0.0005,1.1)', d=1, s='1080x600', x='iw/2-(iw/zoom/2)', y='ih/2-(ih/zoom/2)')
        )
        
        # 3. Layering & Grading
        out = ffmpeg.overlay(bg, fg, y='(H-h)/2')
        
        # 4. Audio-Reactive "Breath" Effect
        out = self.apply_audio_pump(out, audio_peaks, intensity=pump_intensity)

        # 5. Template-Driven Grading
        if template:
            out = self.apply_grading_from_template(out, template)
        else:
            # Fallback legacy grading
            out = out.filter('colorbalance', rs=0.1, bs=-0.1, rm=0.05, bm=-0.05)
            out = out.filter('eq', contrast=1.1, saturation=1.3)
        
        # 6. Cinematic Letterboxing
        out = out.filter('drawbox', x=0, y=0, w='iw', h=100, color='black', t='fill')
        out = out.filter('drawbox', x=0, y='ih-100', w='iw', h=100, color='black', t='fill')
        
        # 7. Kinetic Typography (ASS) - HEADLINE + CAPTIONS consolidated
        if ass_path:
            out = self.apply_ass_subtitles(out, ass_path)
        else:
            out = self.apply_kinetic_captions(out, transcription_data)
        
        return self.apply_progress_bar(out, duration)
