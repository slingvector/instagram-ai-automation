"""
src/ingestion/services/immersive_classifier.py

Classifies content into the "Immersive POV Adrenaline" niche.
Detects:
1. Category (fpv_drone, riding, diving, air_sports, 360_tiny_planet)
2. Motion Intensity (high, medium, low)
3. Perspective (fpv, 360, pov, normal)
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ImmersiveClassifier:
    CATEGORIES = {
        "air_sports": ["skydiving", "wingsuit", "paragliding", "base jump", "air sports"],
        "fpv_drone": ["fpv", "drone", "freestyle", "quadcopter", "betaflight"],
        "riding": ["bike", "motorcycle", "mtb", "dh", "downhill", "ride", "motovlog", "cycling"],
        "diving": ["diving", "surf", "underwater", "wave", "ocean", "sea", "scuba"],
        "360_tiny_planet": ["360", "insta360", "tiny planet", "orbit", "reframe"],
        "sports": ["nba", "nfl", "football", "soccer", "basketball", "highlights", "dunk", "goal", "touchdown", "slam dunk", "hoops", "sports"],
        "fashion": ["fashion", "streetwear", "ootd", "stylish", "runway", "outfit", "couture", "model"],
        "entertainment": ["entertainment", "movie", "pop culture", "celebrity", "showbiz", "trend", "show"],
        "exotic": ["exotic", "luxury", "exotic car", "mansions", "millionaire", "yacht", "villa"]
    }

    MOTION_KEYWORDS = ["fast", "insane", "speed", "crash", "jump", "flip", "adrenaline", "crazy", "unreal"]
    PERSPECTIVE_KEYWORDS = {
        "fpv": ["fpv"],
        "360": ["360", "insta360", "tiny planet"],
        "pov": ["pov", "helmet cam", "chest cam"]
    }

    def classify(self, title: str, keyword: str = "") -> Dict[str, Any]:
        """Heuristic-based classification of content."""
        text = (f"{title} {keyword}").lower()
        
        # 1. Detect Category
        detected_category = "general_adrenaline"
        for cat, keywords in self.CATEGORIES.items():
            if any(k in text for k in keywords):
                detected_category = cat
                break
        
        # 2. Detect Motion (Heuristic)
        motion_score = sum(1 for k in self.MOTION_KEYWORDS if k in text)
        motion = "high" if motion_score >= 2 or "fast" in text or "insane" in text else "medium"
        
        # 3. Detect Perspective
        perspective = "normal"
        for p, keywords in self.PERSPECTIVE_KEYWORDS.items():
            if any(k in text for k in keywords):
                perspective = p
                break
        
        # 4. Immersion Score (0.0 - 1.0)
        immersion_score = 0.5
        if perspective in ["fpv", "360"]: immersion_score += 0.3
        if perspective == "pov": immersion_score += 0.2
        if motion == "high": immersion_score += 0.2
        
        return {
            "type": detected_category,
            "motion": motion,
            "perspective": perspective,
            "immersion_score": min(1.0, immersion_score)
        }
