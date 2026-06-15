import ffmpeg
from typing import Any
from src.media_factory.styles.base_style import BaseStyle

class CinematicPro(BaseStyle):
    """
    High-end cinematic style with heavy grading, letterboxing, and Ken Burns motion.
    Best for: Travel, Storytelling.
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
        
        # 2. Dynamic ROI Framing
        framed = self.apply_roi_framing(v2, roi, iw=width, ih=height)
        
        # 3. Ken Burns zoom (slow 1.1x zoom over time)
        fg = (
            framed
            # Subtle slow zoom
            .filter('zoompan', z='min(zoom+0.0005,1.1)', d=1, s='1080x1920', x='iw/2-(iw/zoom/2)', y='ih/2-(ih/zoom/2)', fps=30)
        )
        
        # 4. Layering & Grading
        out = ffmpeg.overlay(bg, fg, x='(W-w)/2', y='(H-h)/2')
        
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
        
        # 7. High-Fidelity Emoji Overlays (Sprite Engine)
        if burst_manifest:
            out = self.apply_emoji_overlays(out, burst_manifest, audio_peaks=audio_peaks)
            
        # 8. Kinetic Typography (ASS) - HEADLINE + CAPTIONS consolidated
        # Applied LAST to ensure text stays on top of emojis
        if ass_path:
            out = self.apply_ass_subtitles(out, ass_path)
        else:
            out = self.apply_kinetic_captions(out, transcription_data)
        
        return self.apply_progress_bar(out, duration)
