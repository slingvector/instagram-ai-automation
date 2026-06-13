"""
src/media_factory/services/hook_engine.py

Generates high-virality immersive hooks based on content classification.
Strategies:
1. Immersion (POV focus)
2. Impossible (Perspective focus)
3. Experience (Sensation focus)
4. Reality Break (Visual novelty focus)
"""
import random
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class HookEngine:
    HOOKS = {
        "immersion": [
            "POV: You're flying through this",
            "Inside the moment 🎥",
            "This view is addictive",
            "Welcome to the zone",
            "Can you keep up?"
        ],
        "impossible": [
            "This camera should not exist",
            "Angles you've never seen before",
            "Physics? Never heard of it.",
            "Impossible camera movement",
            "Warping reality"
        ],
        "experience": [
            "You can feel this ride 🏍️",
            "Full adrenaline rush",
            "Don't forget to breathe",
            "The ultimate POV experience",
            "This will raise your heart rate"
        ],
        "reality_break": [
            "This doesn't look real",
            "A different perspective",
            "Tiny planet adventure 🌍",
            "Glitch in the matrix",
            "Waking up in a dream"
        ]
    }

    CATEGORY_STRATEGY = {
        "fpv_drone": ["immersion", "impossible"],
        "riding": ["experience", "immersion"],
        "diving": ["immersion", "reality_break"],
        "air_sports": ["experience", "impossible"],
        "360_tiny_planet": ["reality_break", "impossible"]
    }

    def generate_hook(self, immersive_metadata: Dict[str, Any], title: str = "") -> str:
        """Generate a viral headline based on immersive classification."""
        cat = immersive_metadata.get("type", "general_adrenaline")
        
        # Pick strategy based on category
        strategies = self.CATEGORY_STRATEGY.get(cat, ["immersion", "experience"])
        selected_strategy = random.choice(strategies)
        
        # Pick a hook from the selected strategy
        options = self.HOOKS.get(selected_strategy, ["Experience the impossible"])
        hook = random.choice(options)
        
        logger.info(f"HookEngine: Generated '{hook}' for category '{cat}' using strategy '{selected_strategy}'")
        return hook
