import os
import logging
import json
from src.media_factory.services.video_processor_service import VideoProcessorService
from src.orchestration.state_manager import StateManager

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("render_audit_v2")

import tempfile
import ffmpeg
from src.media_factory.styles.style_factory import StyleFactory
from src.media_factory.styles.template_manager import TemplateManager
from src.media_factory.utils.ass_generator import ASSGenerator

def run_local_audit():
    logger.info("🎨 Starting High-Fidelity Emoji Render Audit v2.0...")
    
    # 1. Setup paths
    job_id = "audit_v2_local"
    input_path = os.path.abspath("tests/assets/test_input.mp4")
    niche = "finance"
    headline = "V2.0 HIGH-FIDELITY AUDIT"
    
    if not os.path.exists(input_path):
        logger.error(f"❌ Input video missing: {input_path}")
        return

    # 2. Mock Transcription & Sentiment (The "Golden Data")
    sync_data = {
        "words": [
            {"word": "UNLIMITED", "start": 0.5, "end": 1.5},
            {"word": "SCALE", "start": 1.8, "end": 2.5},
            {"word": "ENGINE", "start": 3.0, "end": 4.5}
        ],
        "sentiment_clusters": [
            {
                "start": 0.0, 
                "end": 3.0, 
                "sentiment": "positive", 
                "text_emojis": "🔥🚀", 
                "reaction_pool": "🔥🚀💸💰💎✨", 
                "burst_count": 12, 
                "intensity": 1.0
            }
        ]
    }
    
    # 3. Initialize Core Components
    template_manager = TemplateManager()
    ass_generator = ASSGenerator()
    
    template_id = template_manager.select_template_by_niche(niche)
    template = template_manager.get_template(template_id)
    
    # Font path (MacOS)
    font_path = "/System/Library/Fonts/Helvetica.ttc"
    style_template = StyleFactory.get_style(niche, font_path)
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        ass_path = os.path.join(tmp_dir, "audit.ass")
        output_path = os.path.abspath("tests/assets/audit_v2_result.mp4")
        
        # 4. Generate ASS & Burst Manifest
        _, burst_manifest = ass_generator.generate(sync_data, ass_path, template=template, headline=headline)
        logger.info(f"✅ Generated ASS and manifest with {len(burst_manifest)} bursts.")

        # 5. FFmpeg Rendering
        logger.info("🎬 Rendering local audit with 512px 3D assets...")
        try:
            probe = ffmpeg.probe(input_path)
            duration = float(probe['format']['duration'])
            width = 720
            height = 1280
            
            input_stream = ffmpeg.input(input_path)
            
            video_out = style_template.apply(
                input_stream, headline, duration,
                roi={'ymin': 0, 'xmin': 0, 'ymax': 1000, 'xmax': 1000},
                transcription_data=sync_data,
                ass_path=ass_path,
                burst_manifest=burst_manifest,
                audio_peaks=[1.0, 2.5, 4.0], # Mock peaks
                width=width,
                height=height,
                template=template
            )
            
            (
                ffmpeg.output(video_out, output_path, vcodec="libx264", crf=23, preset="veryfast")
                .overwrite_output()
                .global_args('-nostdin')
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            logger.info(f"✨ Audit Render COMPLETE: {output_path}")
            
        except ffmpeg.Error as e:
            logger.error(f"❌ FFmpeg Failed: {e.stderr.decode('utf8')}")
        except Exception as e:
            logger.error(f"❌ Local Audio Failed: {e}", exc_info=True)

if __name__ == "__main__":
    # Create mock input if missing for demonstration
    if not os.path.exists("tests/assets"):
        os.makedirs("tests/assets")
    
    run_local_audit()
