import os
import logging
import ffmpeg
from src.media_factory.utils.ass_generator import ASSGenerator
from src.media_factory.styles.style_factory import StyleFactory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_sprite_render():
    """
    Simulates a 5s render with the new Sprite Overlay Engine.
    """
    logger.info("Starting Sprite Overlay Verification...")
    
    # 1. Mock Transcription Data with Burst Clusters
    transcription = {
        "words": [{"word": "SPRITE", "start": 0.5, "end": 1.0}, {"word": "ENGINE", "start": 1.1, "end": 2.0}],
        "sentiment_clusters": [
            {
                "start": 0.5, "end": 2.0, 
                "reaction_pool": "🚀🔥💸", 
                "burst_count": 5, 
                "intensity": 1.0
            }
        ],
        "duration": 5.0
    }
    
    # 2. Generate ASS & Burst Manifest
    ass_path = "data/verify_sprites.ass"
    generator = ASSGenerator()
    _, burst_manifest = generator.generate(transcription, ass_path, headline="SPRITE TEST 2026")
    
    logger.info(f"Generated manifest with {len(burst_manifest)} bursts.")
    
    # 3. Apply Style (Viral Pulse)
    # Pick a system font for base text (Linux-safe fallback)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if os.path.exists("/System/Library/Fonts/Helvetica.ttc"):
        font_path = "/System/Library/Fonts/Helvetica.ttc"
        
    style = StyleFactory.get_style("viral_pulse", font_path)
    
    # 4. Render 5s video
    output_path = "data/sprite_verify_render.mp4"
    input_stream = ffmpeg.input("color=c=black:s=1080x1920:d=5:r=30", f="lavfi")
    
    logger.info(f"Rendering {output_path}...")
    video_out = style.apply(
        input_stream, 
        "SPRITE TEST", 
        5.0, 
        ass_path=ass_path, 
        burst_manifest=burst_manifest,
        width=1080, 
        height=1920
    )
    
    # Robust output with audio (even if silent)
    ffmpeg.output(video_out, output_path, vcodec="libx264", crf=23, preset="ultrafast").overwrite_output().global_args("-nostdin").run()
    
    logger.info(f"✅ VERIFICATION RENDER COMPLETE: {output_path}")
    logger.info("Please inspect data/sprite_verify_render.mp4 for orbiting emoji sprites.")

if __name__ == "__main__":
    verify_sprite_render()
