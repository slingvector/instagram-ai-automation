from google import genai
from google.genai import types
import json
import logging
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# --- Pydantic Schemas for Structured AI Outputs ---

class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float

class SentimentCluster(BaseModel):
    start: float
    end: float
    sentiment: str
    text_emojis: str
    reaction_pool: str
    burst_count: int
    intensity: float

class VideoTranscription(BaseModel):
    words: List[WordTimestamp]
    sentiment_clusters: List[SentimentCluster]

# --- Service Class ---

class VertexAIService:
    """
    Service layer for multimodal video analysis via Gemini.
    Auth priority:
      1. GEMINI_API_KEY env var → Gemini Developer API (free tier via AI Studio)
      2. Vertex AI with GCP service account (requires model access on project)
    Includes a circuit breaker: after 2 consecutive 404s, all calls fail fast.
    """
    _circuit_open = False  # Class-level circuit breaker
    _consecutive_404s = 0
    _CIRCUIT_BREAKER_THRESHOLD = 2

    def __init__(self, project_id: str, location: str = "us-central1"):
        self.project_id = project_id
        self.location = location
        import os
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.is_developer_api = bool(api_key)
        try:
            if self.is_developer_api:
                # Prefer free Gemini Developer API (AI Studio key)
                self.client = genai.Client(api_key=api_key)
                logger.info("Gemini AI Service initialized via API Key (AI Studio / Developer API).")
            else:
                # Fallback to Vertex AI (GCP service account)
                self.client = genai.Client(vertexai=True, project=self.project_id, location=self.location)
                logger.info("Gemini AI Service initialized via Vertex AI (GCP Service Account).")
            self.prompts = self._load_prompts()
        except Exception as e:
            logger.error(f"Failed to initialize Gemini AI: {e}")
            raise

    def _get_video_part(self, gcs_video_uri: str) -> Any:
        """
        Helper to construct the video part based on the API mode.
        Vertex AI supports gs:// URIs natively.
        Developer API (AI Studio) requires uploading the file.
        """
        if not self.is_developer_api:
            return types.Part.from_uri(file_uri=gcs_video_uri, mime_type="video/mp4")
        
        # Download from GCS locally to upload to AI Studio
        import os
        import tempfile
        import time
        from google.cloud import storage
        
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            local_path = tmp.name
        
        try:
            logger.info(f"Downloading {gcs_video_uri} for AI Studio upload...")
            client = storage.Client()
            uri_parts = gcs_video_uri.replace("gs://", "").split("/", 1)
            bucket = client.bucket(uri_parts[0])
            blob = bucket.blob(uri_parts[1])
            blob.download_to_filename(local_path)
            
            logger.info("Uploading video to AI Studio File API...")
            video_file = self.client.files.upload(file=local_path)
            
            logger.info("Waiting for AI Studio to process video...")
            while video_file.state.name == "PROCESSING":
                time.sleep(2)
                video_file = self.client.files.get(name=video_file.name)
            
            if video_file.state.name == "FAILED":
                raise Exception("AI Studio video processing failed.")
                
            return video_file
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

    def _load_prompts(self) -> Dict[str, str]:
        """Loads prompt templates from config/ai_prompts.yaml."""
        import yaml
        import os
        config_path = os.path.join(os.getcwd(), "config", "ai_prompts.yaml")
        if not os.path.exists(config_path):
            logger.warning(f"AI-Prompts: Config not found at {config_path}. Falling back to internal defaults.")
            return {}
        try:
            with open(config_path, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load AI prompts: {e}")
            return {}

    def _close_truncated_json(self, text: str) -> str:
        """
        Attempts to close a truncated JSON string by appending required brackets/braces.
        """
        text = text.strip()
        if not text:
            return "{}"

        # Remove trailing commas that would break parsing
        text = re.sub(r',\s*$', '', text)
        
        stack = []
        i = 0
        in_string = False
        while i < len(text):
            char = text[i]
            if char == '"' and (i == 0 or text[i-1] != '\\'):
                in_string = not in_string
            elif not in_string:
                if char == '{':
                    stack.append('}')
                elif char == '[':
                    stack.append(']')
                elif char == '}':
                    if stack and stack[-1] == '}':
                        stack.pop()
                elif char == ']':
                    if stack and stack[-1] == ']':
                        stack.pop()
            i += 1
        
        # Close open string if truncated inside one
        if in_string:
            text += '"'
            
        # Append needed closing tokens in reverse order
        while stack:
            text += stack.pop()
            
        return text

    def _safe_json_parse(self, text: str) -> Dict[str, Any]:
        """
        Cleans and parses JSON from LLM outputs, handling markdown blocks,
        trailing commas, and other common malformations.
        """
        if not text:
            return {}
        
        cleaned = text.strip()
        
        # 1. Remove Markdown Fencing
        if cleaned.startswith("```"):
            # Find the first newline and last ```
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
            
        # 2. Basic cleaning (trailing commas in objects/arrays)
        import re
        # Remove trailing commas before closing braces/brackets
        cleaned = re.sub(r',\s*([\]}])', r'\1', cleaned)
        
        # 3. Handle single-quote hallucinations (convert to double quotes)
        # This is risky but often necessary if the model ignores the JSON instruction
        # We only do it if the initial parse fails
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            try:
                # Attempt to replace single quotes with double quotes around keys/values
                # Very basic heuristic: 'key': 'value' -> "key": "value"
                hard_cleaned = re.sub(r"'(\w+)'\s*:", r'"\1":', cleaned)
                hard_cleaned = re.sub(r":\s*'([^']*)'", r': "\1"', hard_cleaned)
                return json.loads(hard_cleaned)
            except Exception:
                try:
                    # Final attempt: try closing a truncated JSON
                    recovered = self._close_truncated_json(hard_cleaned)
                    return json.loads(recovered)
                except Exception as inner_e:
                    logger.error(f"Safe JSON Parse failed even after cleaning & recovery. Raw output was: {text[:500]}...")
                    raise inner_e

    def _generate_with_retry(self, model: str, contents: Any, config: Any, max_retries: int = 3) -> Dict[str, Any]:
        """
        Calls Gemini generate_content with retries and safe JSON parsing.
        Includes circuit breaker: if Vertex AI returns 404 repeatedly, fail fast.
        """
        # Circuit breaker: fail immediately if Vertex AI is known to be down
        if VertexAIService._circuit_open:
            raise Exception("Vertex AI circuit breaker OPEN — model not available on this project. Skipping.")

        last_error = None
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
                # Success — reset circuit breaker
                VertexAIService._consecutive_404s = 0
                return self._safe_json_parse(response.text)
            except Exception as e:
                last_error = e
                error_str = str(e)
                # If it's a 404 (model not found), don't waste time retrying
                if '404' in error_str and 'NOT_FOUND' in error_str:
                    VertexAIService._consecutive_404s += 1
                    if VertexAIService._consecutive_404s >= VertexAIService._CIRCUIT_BREAKER_THRESHOLD:
                        VertexAIService._circuit_open = True
                        logger.error("⚡ Vertex AI CIRCUIT BREAKER OPEN: Model not available. All future calls will skip instantly.")
                    raise  # Don't retry 404s — they won't resolve
                logger.warning(f"AI Attempt {attempt + 1}/{max_retries} failed: {e}. Retrying...")
                import time
                time.sleep(2 ** attempt) # Exponential backoff
        
        if last_error:
            raise last_error
        raise Exception("AI failed to generate response after multiple retries.")

    def analyze_video(self, gcs_video_uri: str) -> Dict[str, Any]:
        """
        Sends the GCS Video URI to Gemini 1.5 Flash for analysis.
        Returns a structured JSON dictionary containing extracted viral metadata.
        """
        prompt = self.prompts.get("video_analysis", "You are an expert strategist. Analyze the video and provide JSON with 'caption', 'hashtags', 'burn_in_text'.")

        try:
            logger.info(f"Sending video {gcs_video_uri} to Vertex AI for analysis...")
            
            # Use the helper which handles GCS downloading if in Developer API mode
            video_part = self._get_video_part(gcs_video_uri)
            
            metadata = self._generate_with_retry(
                model='gemini-1.5-flash',
                contents=[video_part, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.7, 
                    max_output_tokens=800
                )
            )
            
            logger.info("Successfully received and parsed Vertex AI metadata.")
            return metadata
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Vertex AI response as JSON: {e}")
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
            video_part = self._get_video_part(gcs_video_uri)
            
            response = self.client.models.generate_content(
                model='gemini-1.5-flash',
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
        prompt = self.prompts.get("roi_detection", "Analyze this video clip and identify the ROI. Respond with JSON: {\"roi\": {...}}")
        try:
            logger.info(f"AI-ROI: Analyzing visual subject in {gcs_video_uri}...")
            video_part = self._get_video_part(gcs_video_uri)
            
            return self._generate_with_retry(
                model='gemini-1.5-flash',
                contents=[video_part, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=500,
                    response_mime_type="application/json"
                )
            )
        except Exception as e:
            logger.error(f"AI-ROI analysis failed: {e}")
            return {"roi": {"ymin": 0, "xmin": 0, "ymax": 1000, "xmax": 1000}, "error": str(e)}
    def transcribe_video_with_timestamps(self, gcs_video_uri: str) -> Dict[str, Any]:
        """
        Uses Gemini 2.0 to generate word-level transcription with timestamps.
        Returns JSON: {"words": [{"word": "Hello", "start": 0.5, "end": 0.8}, ...]}
        """
        prompt = self.prompts.get("transcription_and_vibe", "Analyze the video. Transcribe words and segment into sentiment clusters. Respond with JSON.")
        try:
            logger.info(f"AI-Transcriber: Generating word-level sync for {gcs_video_uri}...")
            video_part = self._get_video_part(gcs_video_uri)
            
            result = self.client.models.generate_content(
                model='gemini-1.5-flash',
                contents=[video_part, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=2048,
                    response_mime_type="application/json",
                    response_schema=VideoTranscription,
                )
            )
            
            # The SDK returns the parsed response text (valid JSON)
            import json
            final_data = json.loads(result.text)
            
            logger.info(f"AI-Transcriber: Received keys: {list(final_data.keys())}")
            if "sentiment_clusters" in final_data:
                logger.info(f"AI-Transcriber: Found {len(final_data['sentiment_clusters'])} sentiment clusters.")
            return final_data
        except Exception as e:
            logger.error(f"AI-Transcriber failed: {e}")
            return {"words": [], "sentiment_clusters": [], "error": str(e)}

    def is_relevant_content(self, text: str, niche: str) -> bool:
        """
        Uses Gemini to determine if a piece of text (caption/title) is 
        relevant to the target niche and is NOT an advertisement or spam.
        """
        template = self.prompts.get("relevance_filter", "Determine if '{text}' is relevant to '{niche}'. Respond RELEVANT or IRRELEVANT.")
        prompt = template.format(text=text, niche=niche)

        try:
            display_text = text[:50] if text else "None"
            logger.info(f"Checking semantic relevance for text: {display_text}...")
            if not text:
                return True # Assume relevant if title is missing (better than dropping)
            response = self.client.models.generate_content(
                model='gemini-1.5-flash',
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
