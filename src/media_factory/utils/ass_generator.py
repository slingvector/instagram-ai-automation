import os
import logging
import random
from typing import Dict, List, Any

import re
logger = logging.getLogger(__name__)

class ASSGenerator:
    """
    Generates Advanced Substation Alpha (.ass) files for kinetic typography.
    Supports word-level animations, highlighting, and dynamic positioning.
    """
    
    # Refined regex: Base + Modifiers, then optionally (ZWJ + Base + Modifiers) sequences
    EMOJI_PATTERN = re.compile(
        r"[\U00002100-\U000027BF\U00010000-\U0010ffff][\ufe0f\uFE00-\uFE0F\u1F3FB-\u1F3FF]*"
        r"(?:\u200d[\U00002100-\U000027BF\U00010000-\U0010ffff][\ufe0f\uFE00-\uFE0F\u1F3FB-\u1F3FF]*)*"
    )
    
    HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FDFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,2,100,100,10,1
Style: Headline,{font_name},65,&H0000E0FF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,0,8,150,150,100,1
Style: Emoji,Noto Color Emoji,120,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,0,0,0,1

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

    def _split_emojis(self, text: str) -> List[str]:
        """Extracts full emoji sequences (including ZWJ) from text."""
        if not text: return []
        return self.EMOJI_PATTERN.findall(text)

    def generate(self, transcription: Dict[str, Any], output_path: str, template: Any = None, headline: str = ""):
        """
        Generates an .ass file with margined paragraph groupings and a top headline.
        Includes Dopamine-Heavy Emoji Layers.
        """
        if not transcription or "words" not in transcription:
            logger.warning("No transcription data for ASS generation.")
            logger.info(f"ASSGenerator: Received transcription keys: {list(transcription.keys())}")
            if "sentiment_clusters" in transcription:
                logger.info(f"ASSGenerator: Found {len(transcription['sentiment_clusters'])} sentiment clusters.")
            return

        if template is None: template = {}
        font_name = template.get("font", self.font_name)
        font_size = template.get("font_size", self.font_size)
        
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
                    "text": str(" ".join(c_words)) if c_words else "",
                    "start": float(c["start"]),
                    "end": float(c["end"]),
                    "sentiment": str(c.get("sentiment", "neutral")),
                    "text_emojis": str(c.get("text_emojis", "")),
                    "reaction_pool": str(c.get("reaction_pool", "")),
                    "burst_count": int(c.get("burst_count", 0)),
                    "intensity": float(c.get("intensity", 0.5))
                })
        else:
            # Fallback chunking
            chunk_size = 3
            for i in range(0, len(words), chunk_size):
                chunk = words[i:i + chunk_size]
                groups.append({
                    "text": str(" ".join([w["word"] for w in chunk])),
                    "start": float(chunk[0]["start"]),
                    "end": float(chunk[-1]["end"]),
                    "text_emojis": "",
                    "floating_emojis": "",
                    "intensity": 0.5
                })
        
        logger.info(f"ASSGenerator: Processed {len(groups)} groups for rendering.")

        burst_manifest = []

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header)
            
            # 2. Render Headline
            if headline:
                max_time = transcription.get("duration")
                if max_time is None: 
                    max_time = float(groups[-1]["end"]) if groups else 60.0
                else:
                    max_time = float(max_time)
                
                start_str, end_str = self._format_time(0.0), self._format_time(max_time)
                h_text: str = str(headline).upper()
                f.write(f"Dialogue: 1,{start_str},{end_str},Headline,,150,150,100,,{{\\an8\\q2}}{h_text}\n")

            # 3. Render Animated Captions & Collect Burst Manifest
            if groups:
                layout = template.get("layout", "center_third") if template else "center_third"
                margin_v = 850 # Higher center for 1920 canvas to avoid spatial crowding
                if layout == "center_lower": margin_v = 400
                if layout == "minimal_lower": margin_v = 300
                
                for group in groups:
                    g_start: float = float(group["start"])
                    g_end: float = float(group["end"])
                    g_intensity: float = float(group["intensity"])
                    
                    start_str = self._format_time(g_start)
                    end_str = self._format_time(g_end + 0.3) 
                    
                    # Layer 0: Main Text (Keeping inline emojis for now, but stripped of font tags if needed)
                    text = str(group["text"]).upper()
                    # Animation Intensity
                    scale = int(100 + (10 * g_intensity))
                    anim_tags = rf"{{\an2\q2\fscx100\fscy100\t(0,100,\fscx{scale}\fscy{scale})\t(100,200,\fscx100\fscy100)}}"
                    
                    f.write(f"Dialogue: 0,{start_str},{end_str},Default,,100,100,{margin_v},,{anim_tags}{text}\n")
                    
                    # Collect Sprite-Based Burst Data
                    reaction_pool = group.get("reaction_pool", "")
                    burst_count = int(group.get("burst_count", 0))
                    
                    if reaction_pool and burst_count > 0:
                        r_pool_str: str = str(reaction_pool)
                        
                        # Support space-separated Semantic Tags (e.g. "vibe_success vibe_fire")
                        # AND raw emoji sequences (e.g. "🔥🚀")
                        raw_items = r_pool_str.split() if "vibe_" in r_pool_str else [r_pool_str]
                        
                        blended_pool = []
                        for item in raw_items:
                            if item.startswith("vibe_"):
                                blended_pool.append(item)
                            else:
                                blended_pool.extend(self._split_emojis(item))
                        
                        # Add universal favorites
                        blended_pool.extend(self._split_emojis(self.UNIVERSAL_EMOJIS))
                        
                        if not blended_pool:
                            blended_pool = ["vibe_heat"] # Fallback to a valid tag
                        
                        for _ in range(burst_count):
                            char = random.choice(blended_pool)
                            jitter = random.uniform(0, 0.5)
                            burst_start: float = g_start + jitter
                            
                            x = random.randint(150, 930)
                            y = random.randint(300, 1620)
                            if 1000 < y < 1400: y += 400 # Avoid caption zone
                            
                            burst_manifest.append({
                                "char": char,
                                "start": burst_start,
                                "end": burst_start + 1.2,
                                "x": x,
                                "y": y,
                                "dx": random.randint(-80, 80),
                                "dy": -random.randint(150, 300),
                                "size": random.randint(120, 240),
                                "intensity": g_intensity,
                                "sentiment": group.get("sentiment", "positive") 
                            })
        
        logger.info(f"ASSGenerator: Generated {output_path} and manifest with {len(burst_manifest)} bursts.")
        return output_path, burst_manifest
