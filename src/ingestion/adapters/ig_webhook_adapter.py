import logging
from typing import Dict, Any

from src.ingestion.repositories.ig_messaging_repository import IGMessagingRepository
from src.ingestion.services.ollama_auto_reply_service import OllamaAutoReplyService

logger = logging.getLogger(__name__)

class IGWebhookAdapter:
    """
    Adapter layer to handle incoming Official Instagram Webhooks.
    Orchestrates the Flow: Receive Comment -> Analyze via LLM -> Reply via Official API.
    Follows SRP by delegating the actual work to the Service and Repository layers.
    """

    def __init__(self):
        self.messaging_repo = IGMessagingRepository()
        self.ollama_service = OllamaAutoReplyService()

    def process_incoming_webhook(self, payload: Dict[str, Any]) -> bool:
        """
        Parses the generic Meta webhook payload.
        If it contains a new comment on a media object, we generate an AI reply.
        """
        try:
            # Meta webhooks can batch multiple entries
            entries = payload.get("entry", [])
            for entry in entries:
                changes = entry.get("changes", [])
                for change in changes:
                    if change.get("field") == "comments":
                        self._handle_new_comment(change.get("value", {}))
            return True
        except Exception as e:
            logger.error(f"Error processing webhook payload: {e}")
            return False

    def _handle_new_comment(self, comment_data: Dict[str, Any]):
        """Extracts the comment text and dispatches the auto-reply."""
        comment_id = comment_data.get("id")
        user_comment = comment_data.get("text")
        media_id = comment_data.get("media", {}).get("id")
        
        # We don't want to reply to our own automated replies
        if comment_data.get("from", {}).get("id") == self.messaging_repo.access_token: # simplified check
             return

        if not comment_id or not user_comment:
            logger.warning("Webhook payload missing comment_id or text.")
            return

        logger.info(f"Received new organic comment on Media {media_id}: '{user_comment}'")

        # 1. Ask locally hosted Ollama what to say
        # In a full PROD scenario, we would query the database for the reel_context using media_id
        reel_context = "A recent Reel about escalating geopolitical tensions and defense tech."
        reply_text = self.ollama_service.generate_comment_reply(user_comment, reel_context)

        # 2. Dispatch the reply back to Instagram via the official API
        logger.info(f"Auto-replying with: '{reply_text}'")
        try:
            self.messaging_repo.reply_to_comment(comment_id, reply_text)
            logger.info("Auto-reply successfully dispatched.")
        except Exception as e:
            logger.error(f"Failed to dispatch auto-reply: {e}")
