import pytest
from unittest.mock import patch
import json
import os

# We need to set the environment variable before importing the function
os.environ["GCP_PROJECT_ID"] = "test-project"

from main import ingest_video
import flask

@pytest.fixture
def client():
    # Create an empty Flask app to act as the context
    app = flask.Flask(__name__)
    return app.test_client()

@patch('controllers.webhook_controller.MediaFactoryTriggerService')
@patch('controllers.webhook_controller.VertexAIService')
@patch('controllers.webhook_controller.JobRepository')
def test_webhook_integration_success(mock_job_repo_class, mock_vertex_service_class, mock_trigger_service_class, client):
    # Mock Vertex Service
    mock_vertex_instance = mock_vertex_service_class.return_value
    mock_vertex_instance.analyze_video.return_value = {
        "caption": "Integration Test Caption",
        "hashtags": ["#test"],
        "burn_in_text": "Integration Hook"
    }

    # Mock Job Repository
    mock_repo_instance = mock_job_repo_class.return_value
    mock_repo_instance.create_job.return_value = "fake-job-id-12345"

    # Mock Trigger Service
    mock_trigger_instance = mock_trigger_service_class.return_value
    mock_trigger_instance.trigger_processing.return_value = True

    # Create a mock flask request context
    app = flask.Flask(__name__)
    with app.test_request_context(
        path='/',
        method='POST',
        json={"gcs_video_uri": "gs://mcr-raw-input/test_video.mp4"}
    ):
        request = flask.request
        response, status_code = ingest_video(request)

        # Assertions
        assert status_code == 200
        response_data = json.loads(response.get_data(as_text=True))
        assert response_data["status"] == "success"
        assert response_data["job_id"] == "fake-job-id-12345"

        # Verify services were called correctly
        mock_vertex_instance.analyze_video.assert_called_once_with("gs://mcr-raw-input/test_video.mp4")
        mock_repo_instance.create_job.assert_called_once()
        mock_trigger_instance.trigger_processing.assert_called_once_with("fake-job-id-12345")
        
def test_webhook_integration_missing_payload(client):
    app = flask.Flask(__name__)
    with app.test_request_context(
        path='/',
        method='POST',
        json={} # No gcs_video_uri
    ):
        request = flask.request
        response, status_code = ingest_video(request)

        # Assertions
        assert status_code == 400
        response_data = json.loads(response.get_data(as_text=True))
        assert "Bad Request" in response_data["error"]
