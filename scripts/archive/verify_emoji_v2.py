import ffmpeg
import os
import json
import logging
import random
from src.media_factory.utils.ass_generator import ASSGenerator
from src.media_factory.styles.style_factory import StyleFactory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sample High-Reactivity Transcription Data
TRANSCRIPTION = {
    "words": [{"word": "DUMMY", "start": 0.0, "end": 0.1}],
    "sentiment_clusters": [
        {
            "start": 0.5,
            "end": 3.5,
            "text": "THIS IS THE NEXT LEVEL OF QUALITY! 🚀🔥",
            "intensity": 9.5,
            "sentiment": "positive",
            "reaction_pool": "🚀🔥✨",
            "burst_count": 8
        },
        {
            "start": 4.0,
            "end": 7.0,
            "text": "Subtle, smooth sinking motion for deep vibes... 💎",
            "intensity": 3.0,
            "sentiment": "neutral",
            "reaction_pool": "💎✨",
            "burst_count": 4
        }
    ]
}

# Mock Rhythmic Audio Peaks (for Beat-Sync Verification)
AUDIO_PEAKS = [0.8, 1.2, 1.6, 2.0, 2.4, 2.8, 3.2, 4.5, 5.5, 6.5]

OUTPUT_DIR = "debug/v2_audit"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def test_render_v2():
    logger.info("🎨 Starting Emoji Engine v2.0 Audit Pass...")
    
    input_video = "data/samples/sample_reel.mp4"
    if not os.path.exists(input_video):
        # Create a dummy colored background if sample missing
        input_video = os.path.join(OUTPUT_DIR, "dummy.mp4")
        ffmpeg.input('color=c=black:s=1080x1920', f='lavfi', t=10).output(input_video).run(overwrite_output=True)

    # 1. Generate Manifest with Sentiment
    template_def = {"layout": "center_third"}
    generator = ASSGenerator()
    ass_path, burst_manifest = generator.generate(
        TRANSCRIPTION, 
        os.path.join(OUTPUT_DIR, "v2_test.ass"),
        template=template_def
    )

    # 2. Render with CinematicPro (v2.0)
    style = StyleFactory.get_style("cinematic_pro", font_path="Arial")
    
    input_stream = ffmpeg.input(input_video)
    duration = 10.0 # Sample duration
    
    logger.info(f"🚀 Rendering v2.0 with {len(burst_manifest)} bursts and Beat-Sync pulses...")
    
    # Process
    video_out = style.apply(
        input_stream, 
        "EMOJI ENGINE V2.0", 
        duration,
        roi={"xmin": 0, "xmax": 1000},
        transcription_data=TRANSCRIPTION,
        ass_path=ass_path,
        burst_manifest=burst_manifest,
        audio_peaks=AUDIO_PEAKS,
        pump_intensity=1.2
    )

    output_path = os.path.join(OUTPUT_DIR, "emoji_v2_validation.mp4")
    
    # Run FFmpeg
    (
        ffmpeg.output(video_out, output_path, vcodec='libx264', pix_fmt='yuv420p', t=duration)
        .run(overwrite_output=True)
    )

    logger.info(f"✅ V2.0 Audit Video Rendered: {output_path}")
    print(f"\nAUDIT COMPLETE: {output_path}")

if __name__ == "__main__":
    test_render_v2()
