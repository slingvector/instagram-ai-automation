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
            "You are a highly skilled social media manager. Watch the attached Instagram Reel. "
            "Please analyze the video and provide the following in pure JSON format:\n"
            "1. 'caption': A high-engagement, witty, and contextual caption.\n"
            "2. 'hashtags': A list of 5-7 viral hashtags relevant to the content.\n"
            "3. 'burn_in_text': A short, catchy phrase (max 5 words) that summarizes the video hook, suitable for burning onto the video screen.\n\n"
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
