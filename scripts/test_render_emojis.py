import ffmpeg
import os
import sys
import tempfile
import logging

# Ensure absolute imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.media_factory.utils.ass_generator import ASSGenerator
from src.media_factory.styles.style_factory import StyleFactory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("emoji_test")

def test_emoji_rendering():
    """
    Renders a 5-second test video with an emoji storm to verify font compatibility.
    """
    output_path = "data/emoji_test_render.mp4"
    os.makedirs("data", exist_ok=True)
    
    # 1. Mock Transcription with many emojis
    transcription = {
        "words": [
            {"word": "Emoji", "start": 0.0, "end": 1.0},
            {"word": "Storm", "start": 1.0, "end": 2.0},
            {"word": "Incoming!", "start": 2.0, "end": 5.0}
        ],
        "sentiment_clusters": [
            {
                "start": 0.0,
                "end": 5.0,
                "text_emojis": "🔥",
                "reaction_pool": "🔥🚀💸💰💎✨🍒🌈",
                "burst_count": 10,
                "intensity": 1.0
            }
        ],
        "duration": 5.0
    }
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        ass_path = os.path.join(tmp_dir, "test.ass")
        logger.info(f"Generating test ASS at {ass_path}...")
        
        generator = ASSGenerator()
        # Use a template that we know has a high burst count
        generator.generate(transcription, ass_path, headline="EMOJI TEST 2026")
        
        # 2. Create a black background video (5s, 9:16)
        logger.info("Creating 5s black background...")
        input_stream = ffmpeg.input(f"color=c=black:s=1080x1920:d=5:r=30", f="lavfi")
        
        # 3. Apply Style (Pick a system font based on OS)
        font_path = "/System/Library/Fonts/Helvetica.ttc"
        if os.name == "posix" and not os.path.exists(font_path):
            font_path = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf" # Fallback to Noto if Helvetica missing
        
        style = StyleFactory.get_style("viral_pulse", font_path)
        
        logger.info(f"Starting FFmpeg render using font: {font_path}")
        video_out = style.apply(
            input_stream, 
            "NOTO EMOJI TEST", 
            5.0, 
            ass_path=ass_path, 
            width=1080, 
            height=1920
        )
        
        try:
            out, err = (
                ffmpeg.output(video_out, output_path, vcodec="libx264", crf=23, preset="ultrafast")
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            logger.info(f"✅ SUCCESS! Test video rendered at: {os.path.abspath(output_path)}")
            if err:
                logger.info("FFmpeg stderr output:")
                print(err.decode('utf8'))
            print(f"\n🚀 TEST COMPLETE: Open {output_path} to verify emojis are not tofu boxes.")
        except ffmpeg.Error as e:
            logger.error(f"❌ RENDER FAILED: {e.stderr.decode('utf8')}")
            sys.exit(1)

if __name__ == "__main__":
    test_emoji_rendering()
