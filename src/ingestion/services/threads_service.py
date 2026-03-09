import logging
from src.ingestion.repositories.threads_graph_repository import ThreadsGraphRepository

logger = logging.getLogger(__name__)

class ThreadsService:
    """
    Service layer for Meta Threads operations.
    Follows SRP and Dependency Inversion. Orchestrates the 2-step API process
    required by Meta (1: Create Container, 2: Publish Container).
    """

    def __init__(self, threads_repository: ThreadsGraphRepository = None):
        self.repo = threads_repository or ThreadsGraphRepository()

    def publish_text_thread(self, text_content: str) -> str:
        """
        Orchestrates publishing a text post to Threads.
        
        Args:
            text_content (str): The body of the Thread post.
            
        Returns:
            str: The ID of the published Thread, or empty string on failure.
        """
        # Threads natively limits text to 500 characters per post. 
        # For an enterprise system, we ensure we truncate gracefully instead of crashing.
        if len(text_content) > 500:
            logger.warning("Thread text exceeds 500 characters. Truncating.")
            text_content = text_content[:497] + "..."

        logger.info(f"Initiating Threads text publish: {text_content[:50]}...")
        
        try:
            # Step 1: Create Container
            container_res = self.repo.create_text_container(text_content)
            creation_id = container_res.get("id")
            if not creation_id:
                logger.error("Failed to acquire creation_id from Threads API.")
                return ""

            # Step 2: Publish Container
            publish_res = self.repo.publish_container(creation_id)
            published_thread_id = publish_res.get("id")
            
            if published_thread_id:
                logger.info(f"Successfully published Thread ID: {published_thread_id}")
                return published_thread_id
            else:
                logger.error("Failed to publish Thread Container.")
                return ""
                
        except Exception as e:
            logger.error(f"Error orchestrating Thread publish: {e}")
            return ""
