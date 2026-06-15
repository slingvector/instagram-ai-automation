import logging
import os
import json
from logging.handlers import RotatingFileHandler
from datetime import datetime

def setup_cloud_logging():
    """
    Configures a Unified Logging Hub:
    1. Standard Output: Human-readable terminal logs.
    2. Local File Rotation: logs/unified_industrial.log (10MB, 5 backups).
    3. Structured Telemetry: logs/telemetry.jsonl for post-run analysis.
    4. GCP Cloud Logging (Optional): Cloud-scale observability.
    """
    project_id = os.getenv("GCP_PROJECT_ID")
    log_dir = os.path.abspath("logs")
    os.makedirs(log_dir, exist_ok=True)

    # 1. Base Configuration (StreamHandler)
    root_logger = logging.getLogger()
    
    # Avoid duplicate handlers if already set up
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    
    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.INFO)

    # 2. Local File Rotation Handler (10MB per file, 5 backups)
    log_file = os.path.join(log_dir, "unified_industrial.log")
    file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 3. Structured Telemetry (JSONL)
    telemetry_file = os.path.join(log_dir, "telemetry.jsonl")
    class JSONLHandler(logging.Handler):
        def emit(self, record):
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "line": record.lineno
            }
            if hasattr(record, "metadata"):
                log_entry["metadata"] = record.metadata
            
            with open(telemetry_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")

    telemetry_handler = JSONLHandler()
    telemetry_handler.setLevel(logging.INFO)
    root_logger.addHandler(telemetry_handler)

    # 4. GCP Cloud Logging (Optional)
    if os.getenv("ENABLE_CLOUD_LOGGING", "false").lower() == "true" and project_id:
        try:
            from google.cloud import logging as cloud_logging
            client = cloud_logging.Client(project=project_id)
            client.setup_logging()
            logging.info("✅ GCP Cloud Logging initialized. Traces are now live.")
        except ImportError:
            logging.warning("google-cloud-logging not installed. Skipping remote tracing.")
        except Exception as e:
            root_logger.error(f"Failed to setup GCP Cloud Logging: {e}")

    logging.info(f"📟 Unified Logger initialized. Local: {log_file} | Telemetry: {telemetry_file}")
