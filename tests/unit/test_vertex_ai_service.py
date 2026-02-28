import pytest
import json
from unittest.mock import patch, MagicMock
from services.vertex_ai_service import VertexAIService

@patch('services.vertex_ai_service.vertexai.init')
@patch('services.vertex_ai_service.GenerativeModel')
def test_vertex_ai_service_success(mock_model_class, mock_init):
    # Setup mock
    mock_model_instance = MagicMock()
    mock_model_class.return_value = mock_model_instance
    
    mock_response = MagicMock()
    mock_response.text = '{"caption": "Viral reel!", "hashtags": ["#viral"], "burn_in_text": "Watch this hook"}'
    mock_model_instance.generate_content.return_value = mock_response
    
    # Execute
    service = VertexAIService(project_id="test-project")
    result = service.analyze_video("gs://test-bucket/video.mp4")
    
    # Assert
    mock_init.assert_called_once_with(project="test-project", location="us-central1")
    assert result['caption'] == "Viral reel!"
    assert result['burn_in_text'] == "Watch this hook"
    assert len(result['hashtags']) == 1

@patch('services.vertex_ai_service.vertexai.init')
@patch('services.vertex_ai_service.GenerativeModel')
def test_vertex_ai_service_markdown_clean(mock_model_class, mock_init):
    # Setup mock with markdown JSON formatting
    mock_model_instance = MagicMock()
    mock_model_class.return_value = mock_model_instance
    
    mock_response = MagicMock()
    mock_response.text = '```json\n{"caption": "Viral reel!"}\n```'
    mock_model_instance.generate_content.return_value = mock_response
    
    # Execute
    service = VertexAIService(project_id="test-project")
    result = service.analyze_video("gs://test-bucket/video.mp4")
    
    # Assert
    assert result['caption'] == "Viral reel!"

@patch('services.vertex_ai_service.vertexai.init')
@patch('services.vertex_ai_service.GenerativeModel')
def test_vertex_ai_service_invalid_json(mock_model_class, mock_init):
    # Setup mock with invalid JSON
    mock_model_instance = MagicMock()
    mock_model_class.return_value = mock_model_instance
    
    mock_response = MagicMock()
    mock_response.text = 'This is not JSON.'
    mock_model_instance.generate_content.return_value = mock_response
    
    # Execute & Assert
    service = VertexAIService(project_id="test-project")
    with pytest.raises(json.JSONDecodeError):
        service.analyze_video("gs://test-bucket/video.mp4")
