import logging
import json
import requests
from typing import Optional

logger = logging.getLogger(__name__)

class OllamaAutoReplyService:
    """
    Business logic layer for generating AI context-aware responses using Local Ollama.
    Follows SRP: This class knows ONLY how to prompt the LLM and parse the output,
    not how the comment was received or how the reply is sent.
    """

    def __init__(self, model: str = "mistral"):
        self.model = model
        self.endpoint = "http://localhost:11434/api/generate"

    def generate_comment_reply(self, user_comment: str, reel_context: str = "") -> str:
        """
        Analyzes the sentiment and context of a user's comment, then generates
        a compliant, human-like short response.
        """
        prompt = f"""
        You are a social media manager for an Instagram account focusing on geopolitical news and history.
        A user just left this comment on a recent Reel: "{user_comment}"
        Context of the Reel: {reel_context}

        Task: Write a short, engaging, and professional 1-sentence reply to this comment. 
        If the comment is negative or toxic, respond politely or ignore the negativity.
        If the user asks for a 'guide' or 'link', reply explicitly telling them to check the link in the bio.
        Do not use hashtags. Be authentic.

        Your Response:
        """

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 50
            }
        }

        try:
            logger.info("Requesting local Ollama for Sentiment Analysis and Reply Generation...")
            response = requests.post(self.endpoint, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            reply_text = data.get("response", "").strip()
            # Clean up quotation marks if Ollama adds them
            reply_text = reply_text.strip('"').strip("'")
            
            if reply_text:
                return reply_text
            return "Thanks for watching!"

        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            # Fallback to a safe generic response to maintain engagement
            return "Great point, thanks for sharing your thoughts!"
