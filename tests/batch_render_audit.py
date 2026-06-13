import os
import logging
import tempfile
import ffmpeg
import random
from src.media_factory.styles.style_factory import StyleFactory
from src.media_factory.styles.template_manager import TemplateManager
from src.media_factory.utils.ass_generator import ASSGenerator
from src.media_factory.services.emoji_sprite_service import EmojiSpriteService

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("batch_audit")

def get_test_videos(target_count: int = 20):
    """Finds available .mp4 files and fulfills target_count using round-robin."""
    potential_dirs = [
        "data",
        "data/downloads",
        "tests/assets",
        "debug/v2_audit"
    ]
    
    unique_videos = []
    for d in potential_dirs:
        abs_d = os.path.abspath(d)
        if not os.path.exists(abs_d):
            continue
        for f in os.listdir(abs_d):
            if f.endswith(".mp4") and "result" not in f and "audit" not in f:
                path = os.path.join(abs_d, f)
                if path not in unique_videos:
                    unique_videos.append(path)
    
    if not unique_videos:
        return []
        
    # Round-Robin to fulfill target_count
    final_videos = []
    for i in range(target_count):
        final_videos.append(unique_videos[i % len(unique_videos)])
        
    return final_videos

def run_batch_audit():
    logger.info("🎨 Starting Batch High-Fidelity Emoji Render Audit v2.0...")
    
    videos = get_test_videos(target_count=20)
    if not videos:
        logger.error("❌ No test videos found.")
        return
    
    logger.info(f"📂 Processing {len(videos)} renders (Round-Robin).")
    
    # Initialize Core Components
    template_manager = TemplateManager()
    ass_generator = ASSGenerator()
    
    output_dir = os.path.abspath("debug/batch_audit")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    font_path = "/System/Library/Fonts/Helvetica.ttc"
    
    success_count = 0
    for i, input_path in enumerate(videos):
        filename = os.path.basename(input_path)
        logger.info(f"[{i+1}/{len(videos)}] Processing: {filename}")
        
        vibe_tags = ["vibe_heat", "vibe_success", "vibe_money", "vibe_energy", "vibe_tech", "vibe_love", "vibe_celebration", "vibe_growth"]
        # Sample 2-4 tags for variety
        simulated_tags = " ".join(random.sample(vibe_tags, random.randint(2, 4)))
        burst_count = random.randint(8, 25) # Stress test it
        
        sync_data = {
            "words": [
                {"word": "BATCH", "start": 0.5, "end": 1.2},
                {"word": "AUDIT", "start": 1.5, "end": 2.2},
                {"word": "SUCCESS", "start": 2.5, "end": 3.5}
            ],
            "sentiment_clusters": [
                {
                    "start": 0.0, 
                    "end": 5.0, 
                    "sentiment": "positive", 
                    "text_emojis": "🔥🚀", 
                    "reaction_pool": simulated_tags, 
                    "burst_count": burst_count, 
                    "intensity": random.uniform(0.7, 1.2)
                }
            ]
        }
        
        niche = random.choice(["finance", "motivation", "tech"])
        headline = f"BATCH AUDIT #{i+1}: {niche.upper()}"
        
        template_id = template_manager.select_template_by_niche(niche)
        template = template_manager.get_template(template_id)
        style_template = StyleFactory.get_style(niche, font_path)
        
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                ass_path = os.path.join(tmp_dir, f"audit_{i}.ass")
                output_path = os.path.join(output_dir, f"audit_result_{i}_{filename}")
                
                # Generate ASS & Burst Manifest
                _, burst_manifest = ass_generator.generate(sync_data, ass_path, template=template, headline=headline)
                
                # FFmpeg Rendering
                probe = ffmpeg.probe(input_path)
                duration = float(probe['format']['duration'])
                video_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
                width = int(video_stream['width']) if video_stream else 720
                height = int(video_stream['height']) if video_stream else 1280
                
                input_stream = ffmpeg.input(input_path)
                
                video_out = style_template.apply(
                    input_stream, headline, duration,
                    roi={'ymin': 0, 'xmin': 0, 'ymax': 1000, 'xmax': 1000},
                    transcription_data=sync_data,
                    ass_path=ass_path,
                    burst_manifest=burst_manifest,
                    audio_peaks=[random.uniform(0.5, 4.5) for _ in range(5)],
                    width=width,
                    height=height,
                    template=template
                )
                
                # Robust stream mapping: check if audio exists
                has_audio = any(s['codec_type'] == 'audio' for s in probe['streams'])
                
                if has_audio:
                    output_stream = ffmpeg.output(video_out, input_stream.audio, output_path, vcodec="libx264", crf=23, preset="veryfast", acodec="aac")
                else:
                    output_stream = ffmpeg.output(video_out, output_path, vcodec="libx264", crf=23, preset="veryfast")

                (
                    output_stream
                    .overwrite_output()
                    .global_args('-nostdin')
                    .run(capture_stdout=True, capture_stderr=True)
                )
                
                logger.info(f"   ✅ Rendered: {output_path}")
                success_count += 1
                
        except Exception as e:
            logger.error(f"   ❌ Failed to process {filename}: {e}")

    logger.info(f"\n🎉 Batch Audit Complete! {success_count}/{len(videos)} videos rendered successfully.")
    logger.info(f"📂 Audit results available in: {output_dir}")

if __name__ == "__main__":
    run_batch_audit()
