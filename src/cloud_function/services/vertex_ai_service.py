from google import genai
from google.genai import types
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class VertexAIService:
    """
    Service layer to interface with Google Vertex AI for multimodal video analysis.
    Uses Gemini 1.5 Flash via the modern google-genai SDK.
    """
    def __init__(self, project_id: str, location: str = "us-central1"):
        self.project_id = project_id
        self.location = location
        try:
            # Initialize the modern python SDK
            self.client = genai.Client(vertexai=True, project=self.project_id, location=self.location)
            logger.info("Vertex AI (google-genai) Service initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI: {e}")
            raise

    def analyze_video(self, gcs_video_uri: str) -> Dict[str, Any]:
        """
        Sends the GCS Video URI to Gemini 1.5 Flash for analysis.
        Returns a structured JSON dictionary containing extracted viral metadata.
        """
        prompt = (
            "You are an expert social media copywriter and viral content strategist. Watch the attached video. "
            "Do not just summarize it blindly. Transform it into a high-retention storytelling asset. "
            "Follow these steps:\n"
            "1. Extract the core raw facts and the most shocking/interesting element.\n"
            "2. Write a high-retention 'caption' that features multi-sentence storytelling. Move away from 1-liners: start with a strong curiosity hook, "
            "tell an engaging story providing context, naturally bake in 3-5 secondary SEO keywords into the text. End with a compelling Call to Action (CTA) "
            "directing viewers to click the link in our bio (e.g., 'Check the link in our bio for 70% off NordVPN!' or 'Read the full uncensored report at the link in our bio!').\n"
            "3. Generate a list of exactly 3-5 highly-targeted 'power tags' for the 'hashtags' array. All hashtags MUST start with the '#' symbol (e.g. '#viral'). Do NOT place any hashtags inside the main 'caption' text.\n"
            "4. Write a punchy 'burn_in_text' (max 5 words) to act as on-screen text overlay that forces the viewer to stop scrolling.\n\n"
            "Provide the output in pure JSON format with the keys: 'caption' (no hashtags here), 'hashtags' (as list of strings WITH the # prefix), and 'burn_in_text'.\n"
            "Respond ONLY with valid JSON. Do not include markdown blocks like ```json."
        )

        try:
            logger.info(f"Sending video {gcs_video_uri} to Vertex AI for analysis...")
            
            # The new genai SDK expects types.Part.from_uri rather than Part.from_uri
            video_part = types.Part.from_uri(file_uri=gcs_video_uri, mime_type="video/mp4")
            
            response = self.client.models.generate_content(
                model='gemini-2.0-flash-001',
                contents=[video_part, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.7, 
                    max_output_tokens=800
                ),
            )
            
            response_text = response.text.strip()
            # Clean up potential markdown formatting if model ignores instruction
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            elif response_text.startswith("```"):
                response_text = response_text.replace("```", "").strip()
                
            metadata = json.loads(response_text)
            logger.info("Successfully received and parsed Vertex AI metadata.")
            return metadata
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Vertex AI response as JSON: {e}\nRaw Response: {response.text}")
            raise
        except Exception as e:
            logger.error(f"Vertex AI API call failed: {e}")
            raise

    def analyze_video_metadata(self, gcs_video_uri: str, prompt: str) -> str:
        """
        Generic method to analyze a video with a custom prompt.
        Returns the raw string response from Gemini.
        """
        try:
            logger.info(f"AI-Metadata: Analyzing {gcs_video_uri} with custom prompt...")
            video_part = types.Part.from_uri(file_uri=gcs_video_uri, mime_type="video/mp4")
            
            response = self.client.models.generate_content(
                model='gemini-2.0-flash-001',
                contents=[video_part, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=1000
                ),
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"AI-Metadata analysis failed: {e}")
            raise

    def analyze_video_roi(self, gcs_video_uri: str) -> Dict[str, Any]:
        """
        Uses Gemini 2.0 to detect the Primary Subject/ROI in the video.
        Uses structured JSON output for robustness.
        """
        prompt = (
            "Analyze this video clip. Identify the 'Primary Subject' that an audience would focus on (e.g., the athlete, the car, the presenter). "
            "Return the normalized bounding box coordinates for this subject at the start, middle, and end of the clip. "
            "Respond ONLY with a JSON object: {\"roi\": {\"ymin\": 0, \"xmin\": 0, \"ymax\": 1000, \"xmax\": 1000}, \"tracking_notes\": \"string\"}"
        )
        try:
            logger.info(f"AI-ROI: Analyzing visual subject in {gcs_video_uri}...")
            video_part = types.Part.from_uri(file_uri=gcs_video_uri, mime_type="video/mp4")
            
            response = self.client.models.generate_content(
                model='gemini-2.0-flash-001',
                contents=[video_part, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json"
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"AI-ROI analysis failed: {e}")
            return {"roi": {"ymin": 0, "xmin": 0, "ymax": 1000, "xmax": 1000}, "error": str(e)}
    def transcribe_video_with_timestamps(self, gcs_video_uri: str) -> Dict[str, Any]:
        """
        Uses Gemini 2.0 to generate word-level transcription with timestamps.
        Returns JSON: {"words": [{"word": "Hello", "start": 0.5, "end": 0.8}, ...]}
        """
        prompt = (
            "Analyze the emotional 'vibe' and visual sentiment of this video. "
            "1. Transcribe any spoken words with precise timestamps. "
            "2. CRITICAL: Segment the ENTIRE video into 'sentiment_clusters' (approx 3-5 seconds each), covering the total duration. "
            "For EACH cluster (even if no words are spoken), you MUST provide:\n"
            "   - 'start' and 'end' timestamps (seconds).\n"
            "   - 'text_emojis': 2-3 emojis reflecting the vibe.\n"
            "   - 'reaction_pool': A string of 5-10 distinct emojis for 'burst' effects.\n"
            "   - 'burst_count': Integer (3-8) for simultaneous pop-ups.\n"
            "   - 'intensity': Float (0.0 to 1.0).\n\n"
            "Respond ONLY with a JSON object in this format:\n"
            "{\"words\": [{\"word\": \"text\", \"start\": 0.0, \"end\": 0.5}], "
            "\"sentiment_clusters\": [{\"start\": 0.0, \"end\": 3.0, \"text_emojis\": \"🔥🚀\", \"reaction_pool\": \"🔥🚀💸💰💎✨\", \"burst_count\": 5, \"intensity\": 0.9}]}"
        )
        try:
            logger.info(f"AI-Transcriber: Generating word-level sync for {gcs_video_uri}...")
            video_part = types.Part.from_uri(file_uri=gcs_video_uri, mime_type="video/mp4")
            
            response = self.client.models.generate_content(
                model='gemini-2.0-flash-001',
                contents=[video_part, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json"
                ),
            )
            
            result = json.loads(response.text)
            logger.info(f"AI-Transcriber: Received keys: {list(result.keys())}")
            if "sentiment_clusters" in result:
                logger.info(f"AI-Transcriber: Found {len(result['sentiment_clusters'])} sentiment clusters.")
            else:
                logger.warning("AI-Transcriber: MISSING sentiment_clusters in response!")
            return result
        except Exception as e:
            logger.error(f"AI-Transcriber failed: {e}")
            return {"words": [], "error": str(e)}

    def is_relevant_content(self, text: str, niche: str) -> bool:
        """
        Uses Gemini to determine if a piece of text (caption/title) is 
        relevant to the target niche and is NOT an advertisement or spam.
        """
        prompt = (
            f"You are a content quality filter for a geopolitics and global news page. "
            f"Analyze the following text and determine if it is relevant to the '{niche}' niche. "
            "Also, check if it is a promotional advertisement (e.g., VPNs, gaming, products) or low-quality spam.\n\n"
            "Rules:\n"
            "- If it is purely about global events, policy, conflict, or history related to the niche: RELEVANT\n"
            "- If it is an ad, promotional, or completely unrelated: IRRELEVANT\n\n"
            f"Text: \"{text}\"\n\n"
            "Respond ONLY with 'RELEVANT' or 'IRRELEVANT'."
        )

        try:
            display_text = text[:50] if text else "None"
            logger.info(f"Checking semantic relevance for text: {display_text}...")
            if not text:
                return True # Assume relevant if title is missing (better than dropping)
            response = self.client.models.generate_content(
                model='gemini-2.0-flash-001',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0, # Deterministic
                    max_output_tokens=10
                ),
            )
            decision = response.text.strip().upper()
            is_relevant = "RELEVANT" in decision and "IRRELEVANT" not in decision
            logger.info(f"Relevance Decision: {decision} ({is_relevant})")
            return is_relevant
        except Exception as e:
            logger.error(f"Vertex AI relevance check failed: {e}")
            return True # Fallback to true to avoid dropping content on API failure
