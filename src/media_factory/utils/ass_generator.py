import os
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class ASSGenerator:
    """
    Generates Advanced Substation Alpha (.ass) files for kinetic typography.
    Supports word-level animations, highlighting, and dynamic positioning.
    """
    
    HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FDFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,2,2,100,100,10,1
Style: Headline,{font_name},60,&H0000E0FF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,2,8,150,150,150,1
Style: Emoji,Apple Color Emoji,120,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    UNIVERSAL_EMOJIS = "❤️🔥😂🙌✨😍💸🚀👏💎✅" # Instagram/WhatsApp story favorites
    
    def __init__(self, font_name: str = "Arial", font_size: int = 70):
        self.font_name = font_name
        self.font_size = font_size

    def _format_time(self, seconds: float) -> str:
        """Formats seconds to ASS time format (H:MM:SS.cs)."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds * 100) % 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    def generate(self, transcription: Dict[str, Any], output_path: str, template: Dict[str, Any] = None, headline: str = None):
        """
        Generates an .ass file with margined paragraph groupings and a top headline.
        Includes Dopamine-Heavy Emoji Layers.
        """
        import random
        if not transcription or "words" not in transcription:
            logger.warning("No transcription data for ASS generation.")
            logger.info(f"ASSGenerator: Received transcription keys: {list(transcription.keys())}")
            if "sentiment_clusters" in transcription:
                logger.info(f"ASSGenerator: Found {len(transcription['sentiment_clusters'])} sentiment clusters.")
            return

        font_name = template.get("font", self.font_name) if template else self.font_name
        font_size = template.get("font_size", self.font_size) if template else self.font_size
        
        header = self.HEADER.format(
            font_name=font_name,
            font_size=font_size
        )

        # 1. Grouping Logic: Use sentiment clusters if available, else chunk words
        words = transcription["words"]
        clusters = transcription.get("sentiment_clusters", [])
        
        groups = []
        if clusters:
            # Match words to clusters
            for c in clusters:
                # LOOSER MATCHING: Allow words that overlap significantly with the cluster
                c_words = [w["word"] for w in words if w["start"] >= c["start"] - 0.5 and w["start"] <= c["end"]]
                
                # SUPPORT SILENT SEGMENTS: Always add the group if it's a cluster, even with 0 words
                groups.append({
                    "text": " ".join(c_words) if c_words else "",
                    "start": c["start"],
                    "end": c["end"],
                    "text_emojis": c.get("text_emojis", ""),
                    "reaction_pool": c.get("reaction_pool", ""),
                    "burst_count": c.get("burst_count", 0),
                    "intensity": c.get("intensity", 0.5)
                })
        else:
            # Fallback chunking
            chunk_size = 3
            for i in range(0, len(words), chunk_size):
                chunk = words[i:i + chunk_size]
                groups.append({
                    "text": " ".join([w["word"] for w in chunk]),
                    "start": chunk[0]["start"],
                    "end": chunk[-1]["end"],
                    "text_emojis": "",
                    "floating_emojis": "",
                    "intensity": 0.5
                })
        
        logger.info(f"ASSGenerator: Processed {len(groups)} groups for rendering.")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header)
            
            # 2. Render Headline
            if headline:
                max_time = transcription.get("duration", 60.0)
                if not max_time: max_time = groups[-1]["end"] if groups else 60.0
                start_str, end_str = self._format_time(0.0), self._format_time(max_time)
                f.write(f"Dialogue: 0,{start_str},{end_str},Headline,,0,0,0,,{{\\an8\\q2}}{headline.upper()}\n")

            # 3. Render Animated Captions & Emojis
            if groups:
                layout = template.get("layout", "center_third") if template else "center_third"
                margin_v = 720 # Default
                if layout == "center_lower": margin_v = 320
                if layout == "minimal_lower": margin_v = 250
                
                anim_type = template.get("animation", "pop") if template else "pop"
                
                for group in groups:
                    start_str = self._format_time(group["start"])
                    end_str = self._format_time(group["end"] + 0.3) # Snappier buffer
                    
                    # Layer 0: Main Text + Embedded Emojis
                    text = group["text"].upper()
                    if group["text_emojis"]:
                        # Font-switch for emojis - use \fnEmoji for style sync
                        text += rf" {{\fnEmoji}}{group['text_emojis']}{{\fn{font_name}}}"
                    
                    # Animation Intensity
                    scale = int(100 + (10 * group["intensity"]))
                    anim_tags = rf"{{\an2\q2\fscx100\fscy100\t(0,100,\fscx{scale}\fscy{scale})\t(100,200,\fscx100\fscy100)}}"
                    
                    f.write(f"Dialogue: 0,{start_str},{end_str},Default,,100,100,{margin_v},,{anim_tags}{text}\n")
                    
                    # Layer 1: Burst Mode (Story-Pop Style)
                    reaction_pool = group.get("reaction_pool", "")
                    burst_count = int(group.get("burst_count", 0))
                    
                    if reaction_pool and burst_count > 0:
                        # UNIVERSAL SYNERGY: Mix in story-favorites
                        blended_pool = list(reaction_pool) + list(self.UNIVERSAL_EMOJIS)
                        
                        for _ in range(burst_count):
                            char = random.choice(blended_pool)
                            jitter = random.uniform(0, 0.5)
                            burst_start = group["start"] + jitter
                            burst_end = burst_start + 1.2
                            
                            b_start_str = self._format_time(burst_start)
                            b_end_str = self._format_time(burst_end)
                            
                            x = random.randint(150, 930)
                            y = random.randint(300, 1620)
                            if 1000 < y < 1400: y += 400
                            
                            x2, y2 = x + random.randint(-80, 80), y - random.randint(150, 300)
                            size = random.randint(80, 160)
                            
                            # Use \fnEmoji consistently for burst layers
                            floating_tags = (
                                rf"{{\an5\fs{size}\fnEmoji\fscx0\fscy0"
                                rf"\t(0,150,\fscx180\fscy180)\t(150,300,\fscx100\fscy100)"
                                rf"\t(800,1200,\alpha&HFF&)"
                                rf"\move({x},{y},{x2},{y2})}}"
                            )
                            f.write(f"Dialogue: 1,{b_start_str},{b_end_str},Emoji,,0,0,0,,{floating_tags}{char}\n")
        
        logger.info(f"Ultra-Pro v2.5: Generated consolidated ASS: {output_path}")
