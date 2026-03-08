import logging
import os

def setup_cloud_logging():
    """
    Configures Python's root logger to asynchronously send logs to Google Cloud Logging.
    This enables centralized observability and self-healing error analysis.
    """
    if os.getenv("ENABLE_CLOUD_LOGGING", "false").lower() != "true":
        return

    try:
        from google.cloud import logging as cloud_logging
        
        project_id = os.getenv("GCP_PROJECT_ID")
        if not project_id:
            logging.warning("GCP_PROJECT_ID not set; skipping Cloud Logging setup.")
            return
            
        # Initialize Google Cloud Logging client
        client = cloud_logging.Client(project=project_id)
        
        # Attaches a CloudLoggingHandler to the root logger
        client.setup_logging()
        
        logging.getLogger(__name__).info("✅ GCP Cloud Logging initialized. Traces are now live.")
    except ImportError:
        logging.warning("google-cloud-logging not installed. Skipping remote tracing.")
    except Exception as e:
        logging.error(f"Failed to setup GCP Cloud Logging: {e}")
