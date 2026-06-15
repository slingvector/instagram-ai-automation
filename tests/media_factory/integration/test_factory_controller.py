import pytest
import os
import flask
from unittest.mock import patch

# Set required environment variables before import
os.environ["GCP_PROJECT_ID"] = "test-project"

from src.media_factory.main import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@patch('src.media_factory.controllers.factory_controller.ProcessedJobRepository')
@patch('src.media_factory.controllers.factory_controller.VideoProcessorService')
def test_factory_webhook_success(mock_video_service_class, mock_repo_class, client):
    # Setup Mocks
    mock_repo = mock_repo_class.return_value
    mock_repo.get_job.return_value = {
        "gcs_raw_video_uri": "gs://test/video.mp4",
        "ai_metadata": {"burn_in_text": "Viral Hook!"}
    }
    
    mock_video_service = mock_video_service_class.return_value
    mock_video_service.apply_burn_in.return_value = "gs://test/processed.mp4"

    # Execute
    response = client.post('/', json={"job_id": "job123"})
    
    # Assert
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["processed_video_uri"] == "gs://test/processed.mp4"
    
    # Verify interactions
    mock_repo.get_job.assert_called_once_with("job123")
    mock_video_service.apply_burn_in.assert_called_once_with("gs://test/video.mp4", "Viral Hook!", "job123")
    mock_repo.mark_job_completed.assert_called_once_with("job123", "gs://test/processed.mp4")

@patch('src.media_factory.controllers.factory_controller.ProcessedJobRepository')
def test_factory_job_not_found(mock_repo_class, client):
    mock_repo = mock_repo_class.return_value
    mock_repo.get_job.return_value = None
    
    response = client.post('/', json={"job_id": "missing_job"})
    
    assert response.status_code == 404
    assert "Job not found" in response.get_json()["error"]
