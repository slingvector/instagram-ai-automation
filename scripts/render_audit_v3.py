import os
import logging
import json
import tempfile
import ffmpeg
import random
from src.media_factory.styles.style_factory import StyleFactory
from src.media_factory.styles.template_manager import TemplateManager
from src.media_factory.utils.ass_generator import ASSGenerator

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("render_audit_v3")

def run_local_audit_v3():
    logger.info("🎨 Starting High-Fidelity Media Engine Audit v3.0...")
    
    # 1. Setup paths
    input_path = os.path.abspath("data/emoji_stress_test.mp4")
    niche = "finance"
    headline = "v3.0 ORGANIC PHYSICS AUDIT"
    output_path = os.path.abspath("tests/assets/audit_v3_result.mp4")
    
    if not os.path.exists(input_path):
        logger.error(f"❌ Input video missing: {input_path}")
        return

    # 2. Mock Transcription & Sentiment (v3.0 Target Intelligence)
    sync_data = {
        "words": [
            {"word": "ORGANIC", "start": 0.5, "end": 1.2},
            {"word": "BUBBLE", "start": 1.3, "end": 2.2},
            {"word": "DRIFT", "start": 2.5, "end": 4.5}
        ],
        "sentiment_clusters": [
            {
                "start": 0.0, 
                "end": 5.0, 
                "sentiment": "positive", 
                "text_emojis": "🔥🚀💎", 
                "reaction_pool": "vibe_success vibe_money vibe_energy", 
                "burst_count": 15, 
                "intensity": 1.2
            }
        ]
    }
    
    # 3. Initialize Core Components
    template_manager = TemplateManager()
    ass_generator = ASSGenerator()
    
    template_id = template_manager.select_template_by_niche(niche)
    template = template_manager.get_template(template_id)
    
    # Switch to a premium font style if we want to force it for the audit
    template['font'] = "Arial Black" # Ensure visibility for audit
    
    # Font path (MacOS)
    font_path = "/System/Library/Fonts/Helvetica.ttc"
    style_template = StyleFactory.get_style(niche, font_path)
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        ass_path = os.path.join(tmp_dir, "audit_v3.ass")
        
        # 4. Generate ASS & Burst Manifest
        _, burst_manifest = ass_generator.generate(sync_data, ass_path, template=template, headline=headline)
        logger.info(f"✅ Generated ASS and manifest with {len(burst_manifest)} bursts.")

        # 5. FFmpeg Rendering
        logger.info(f"🎬 Rendering v3.0 audit (Physics: Trigonometric)...")
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
                audio_peaks=[1.0, 2.5, 4.0],
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
            
            logger.info(f"✨ v3.0 Audit Render COMPLETE: {output_path}")
            
        except ffmpeg.Error as e:
            logger.error(f"❌ FFmpeg Failed: {e.stderr.decode('utf8')}")
        except Exception as e:
            logger.error(f"❌ Render Failed: {e}", exc_info=True)

if __name__ == "__main__":
    run_local_audit_v3()
