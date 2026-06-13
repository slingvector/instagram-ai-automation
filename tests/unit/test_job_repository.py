import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from src.cloud_function.repositories.job_repository import JobRepository


@patch('src.cloud_function.repositories.job_repository.firestore.Client')
def test_create_job_success(mock_client_class):
    # Setup mock
    mock_db = MagicMock()
    mock_client_class.return_value = mock_db
    
    mock_collection = MagicMock()
    mock_db.collection.return_value = mock_collection
    
    mock_document = MagicMock()
    mock_collection.document.return_value = mock_document
    
    # Execute
    repo = JobRepository(project_id="test-project")
    metadata = {"caption": "Test"}
    job_id = repo.create_job("gs://test/video.mp4", metadata)
    
    # Assert
    assert job_id is not None
    mock_db.collection.assert_called_once_with("job_queue")
    mock_document.set.assert_called_once()
    
    # Verify the payload structure that was passed to set()
    call_args = mock_document.set.call_args[0][0]
    assert call_args["job_id"] == job_id
    assert call_args["gcs_raw_video_uri"] == "gs://test/video.mp4"
    assert call_args["ai_metadata"] == metadata
    assert call_args["status"] == "PENDING_MEDIA_FACTORY"

@patch('src.cloud_function.repositories.job_repository.firestore.Client')
def test_create_job_failure(mock_client_class):
    # Setup mock to simulate a database write error
    mock_db = MagicMock()
    mock_client_class.return_value = mock_db
    
    mock_collection = MagicMock()
    mock_db.collection.return_value = mock_collection
    
    mock_document = MagicMock()
    mock_document.set.side_effect = Exception("Firestore write failed")
    mock_collection.document.return_value = mock_document
    
    # Execute & Assert
    repo = JobRepository(project_id="test-project")
    with pytest.raises(Exception):
        repo.create_job("gs://test/video.mp4", {})
