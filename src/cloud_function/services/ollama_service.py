import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any

logger = logging.getLogger(__name__)

class OllamaService:
    """
    Local AI fallback using Ollama. Used when Vertex AI hits quota limits (429).
    Since Ollama Vision models are slow and heavy for full videos, this text-based
    fallback generates high-retention copy purely from the video's title and metadata.
    """
    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3.2"):
        self.host = host
        self.model = model
        
    def generate_copy_from_metadata(self, title: str, context: str = "") -> Dict[str, Any]:
        """
        Prompts local Ollama to generate the IG Reel JSON payload based on the video title.
        """
        logger.info(f"Using Local Ollama ({self.model}) for AI Copywriting fallback...")
        
        prompt = (
            f"You are an expert social media copywriter. I am posting a viral Instagram Reel. "
            f"The video is about: '{title}'. Additional context: '{context}'.\n\n"
            "Based on this topic, transform it into a high-retention storytelling asset. "
            "Follow these exact steps:\n"
            "1. Write a high-retention 'caption' that features multi-sentence storytelling. Move away from 1-liners: start with a strong curiosity hook, "
            "tell an engaging story providing context, naturally bake in 3-5 secondary SEO keywords into the text. End with a compelling Call to Action (CTA) "
            "directing viewers to click the link in our bio (e.g., 'Check the link in our bio for 70% off NordVPN!' or 'Read the full uncensored report at the link in our bio!').\n"
            "2. Generate exactly 3-5 highly-targeted 'power tags' for the 'hashtags' array. All hashtags MUST start with the '#' symbol (e.g. '#viral'). Do NOT place any hashtags inside the main 'caption' text.\n"
            "3. Write a punchy 'burn_in_text' (max 5 words) to act as on-screen text overlay that forces the viewer to stop scrolling.\n\n"
            "Provide the output in pure JSON format exactly with keys: 'caption' (no hashtags here), 'hashtags' (list of strings WITH the # prefix), 'burn_in_text'.\n"
            "Respond ONLY with valid JSON. Not markdown."
        )

        url = f"{self.host}/api/generate"
        paylaod = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.7}
        }
        
        req = urllib.request.Request(url, data=json.dumps(paylaod).encode('utf-8'), 
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode('utf-8'))
                
            response_text = result.get("response", "").strip()
            # Clean possible markdown block
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            elif response_text.startswith("```"):
                response_text = response_text.replace("```", "").strip()

            # Sanitize invalid Unicode escapes (e.g. \uXXXX with non-hex chars)
            import re
            response_text = re.sub(r'\\u(?![0-9a-fA-F]{4})[^"]{0,4}', '', response_text)
                
            metadata = json.loads(response_text)
            logger.info("Successfully generated AI copy via local Ollama.")
            return metadata
            
        except urllib.error.URLError as e:
            logger.error(f"Cannot connect to local Ollama (is it running?): {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Ollama returned invalid JSON: {e}\nRaw: {response_text}")
            raise
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise
