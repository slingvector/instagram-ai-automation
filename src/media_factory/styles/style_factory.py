import logging
from src.media_factory.styles.cinematic_pro import CinematicPro
from src.media_factory.styles.viral_pulse import ViralPulse
from src.media_factory.styles.the_visionary import TheVisionary

logger = logging.getLogger(__name__)

class StyleFactory:
    """
    Maps video niche/content-type to a specific Ultra-Pro Style.
    """
    @staticmethod
    def get_style(niche: str, font_path: str):
        niche = niche.lower()
        
        # Mapping logic
        if any(keyword in niche for keyword in ["travel", "outdoor", "lifestyle", "story", "beauty", "nature", "fashion", "entertainment", "exotic"]):
            logger.info(f"StyleFactory: Selected 'CinematicPro' for niche '{niche}'")
            return CinematicPro(font_path)
        
        if any(keyword in niche for keyword in ["sports", "cricket", "badminton", "tech", "news", "stock", "podcast", "wealth"]):
            logger.info(f"StyleFactory: Selected 'ViralPulse' for niche '{niche}'")
            return ViralPulse(font_path)
            
        # Default for anything else (using AI-Guided Reframe)
        logger.info(f"StyleFactory: Selected 'TheVisionary' (Default) for niche '{niche}'")
        return TheVisionary(font_path)
