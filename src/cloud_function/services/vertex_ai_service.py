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
            "tell an engaging story providing context, naturally bake in 3-5 secondary SEO keywords into the text, and end with a call to action.\n"
            "3. Generate a list of exactly 3-5 highly-targeted 'power tags' for the 'hashtags' array. All hashtags MUST be strictly lowercase.\n"
            "4. Write a punchy 'burn_in_text' (max 5 words) to act as on-screen text overlay that forces the viewer to stop scrolling.\n\n"
            "Provide the output in pure JSON format with the keys: 'caption', 'hashtags' (as list of strings without #), and 'burn_in_text'.\n"
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
