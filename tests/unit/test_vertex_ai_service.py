import pytest
import json
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from src.cloud_function.services.vertex_ai_service import VertexAIService


@patch('src.cloud_function.services.vertex_ai_service.genai.Client')
def test_vertex_ai_service_success(mock_client_class):
    # Setup mock
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.text = '{"caption": "Viral reel!", "hashtags": ["#viral"], "burn_in_text": "Watch this hook"}'
    mock_client.models.generate_content.return_value = mock_response
    
    # Execute
    service = VertexAIService(project_id="test-project")
    result = service.analyze_video("gs://test-bucket/video.mp4")
    
    # Assert
    mock_client_class.assert_called_once_with(
        vertexai=True, project="test-project", location="us-central1"
    )
    assert result['caption'] == "Viral reel!"
    assert result['burn_in_text'] == "Watch this hook"
    assert len(result['hashtags']) == 1


@patch('src.cloud_function.services.vertex_ai_service.genai.Client')
def test_vertex_ai_service_markdown_clean(mock_client_class):
    # Setup mock with markdown JSON formatting
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.text = '```json\n{"caption": "Viral reel!"}\n```'
    mock_client.models.generate_content.return_value = mock_response
    
    # Execute
    service = VertexAIService(project_id="test-project")
    result = service.analyze_video("gs://test-bucket/video.mp4")
    
    # Assert
    assert result['caption'] == "Viral reel!"


@patch('src.cloud_function.services.vertex_ai_service.genai.Client')
def test_vertex_ai_service_invalid_json(mock_client_class):
    # Setup mock with invalid JSON
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.text = 'This is not JSON.'
    mock_client.models.generate_content.return_value = mock_response
    
    # Execute & Assert
    service = VertexAIService(project_id="test-project")
    with pytest.raises(json.JSONDecodeError):
        service.analyze_video("gs://test-bucket/video.mp4")
