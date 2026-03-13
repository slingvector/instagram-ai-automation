import yaml
import os
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class TemplateManager:
    """
    Manages the library of 100+ creator-grade templates.
    """
    def __init__(self, config_path: str = None):
        if not config_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "configs", "templates.yaml")
        
        self.config_path = config_path
        self.templates = self._load_templates()

    def _load_templates(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            logger.error(f"Template config not found: {self.config_path}")
            return {}
        
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
                return config.get("templates", {})
        except Exception as e:
            logger.error(f"Failed to load templates: {e}")
            return {}

    def get_template(self, template_id: str) -> Dict[str, Any]:
        """Returns a template by ID, or a default if not found."""
        template = self.templates.get(template_id)
        if not template:
            logger.warning(f"Template '{template_id}' not found. Using 'beast_impact' as fallback.")
            return self.templates.get("beast_impact", {})
        return template

    def list_templates(self) -> List[Dict[str, str]]:
        """Lists all available templates with descriptions."""
        return [
            {"id": tid, "description": t.get("description", "")}
            for tid, t in self.templates.items()
        ]

    def select_template_by_niche(self, niche: str) -> str:
        """
        AI-ready logic to map a niche string to the best matching template ID.
        Uses randomized pooling for aesthetic variety.
        """
        import random
        niche = niche.lower()
        
        # Define pools for each niche category
        pools = {
            "business": ["hormozi_bold", "beast_impact", "finance_slick"],
            "finance": ["finance_slick", "pulse_investor", "abdaal_minimal"],
            "tech": ["tech_noir", "neo_tokyo_glitch", "abdaal_minimal"],
            "history": ["history_monolith", "geopolitical_steel"],
            "sports": ["court_clash", "beast_impact", "pulse_investor"],
            "news": ["geopolitical_steel", "finance_slick", "pulse_investor", "tech_noir"],
            "viral": ["capcut_vibe", "beast_impact", "pulse_investor"],
            "nature": ["zen_lifestyle", "beauty_standard", "insta360_motion"],
            "podcast": ["podcast_guru", "abdaal_minimal", "hormozi_bold"],
            "beauty": ["beauty_standard", "zen_lifestyle"]
        }

        # Match niche to pool
        selected_pool = None
        if any(w in niche for w in ["business", "wealth", "money", "rich"]):
            selected_pool = pools["business"]
        elif any(w in niche for w in ["finance", "trading", "stocks"]):
            selected_pool = pools["finance"]
        elif any(w in niche for w in ["tech", "future", "ai", "coding", "code"]):
            selected_pool = pools["tech"]
        elif any(w in niche for w in ["history", "war", "museum", "ancient", "military"]):
            selected_pool = pools["history"]
        elif any(w in niche for w in ["badminton", "tennis", "sports", "athlete", "cricket"]):
            selected_pool = pools["sports"]
        elif any(w in niche for w in ["news", "politics", "current", "war"]):
            selected_pool = pools["news"]
        elif any(w in niche for w in ["viral", "funny", "meme", "entertainment"]):
            selected_pool = pools["viral"]
        elif any(w in niche for w in ["nature", "travel", "calm", "relax"]):
            selected_pool = pools["nature"]
        elif any(w in niche for w in ["podcast", "interview", "motivational"]):
            selected_pool = pools["podcast"]
        elif any(w in niche for w in ["beauty", "skincare", "lifestyle", "aesthetic"]):
            selected_pool = pools["beauty"]
            
        if selected_pool:
            template_id = random.choice(selected_pool)
            logger.info(f"TemplateManager: Randomly selected '{template_id}' from pool for niche '{niche}'")
            return template_id
            
        return "beast_impact" # Default high-retention
