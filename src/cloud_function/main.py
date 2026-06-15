import functions_framework
from src.cloud_function.controllers.webhook_controller import process_webhook

@functions_framework.http
def ingest_video(request):
    """
    HTTP Cloud Function entry point.
    Receives JSON payload containing a GCS URI of a raw video.
    """
    return process_webhook(request)
