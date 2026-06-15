import pytest
from unittest.mock import patch, MagicMock
from src.media_factory.services.video_processor_service import VideoProcessorService

@patch('services.video_processor_service.storage.Client')
@patch('services.video_processor_service.ffmpeg')
@patch('services.video_processor_service.tempfile.TemporaryDirectory')
def test_apply_burn_in_success(mock_temp_dir, mock_ffmpeg, mock_storage_client):
    # Setup Storage Mocks
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_storage_client.return_value.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob
    
    # Setup Temp Dir Mock
    mock_temp_instance = MagicMock()
    mock_temp_instance.__enter__.return_value = '/tmp/fake_dir'
    mock_temp_dir.return_value = mock_temp_instance
    
    # Setup FFmpeg Builder Chain Mock
    mock_input = MagicMock()
    mock_output = MagicMock()
    mock_overwrite = MagicMock()
    mock_run = MagicMock()
    
    mock_ffmpeg.input.return_value = mock_input
    mock_input.output.return_value = mock_output
    mock_output.overwrite_output.return_value = mock_overwrite
    mock_overwrite.run.return_value = mock_run

    # Execute
    service = VideoProcessorService(project_id="test-project")
    result_uri = service.apply_burn_in("gs://test-bucket/raw.mp4", "Watch me!", "job123")
    
    # Assert Storage interactions
    assert mock_bucket.blob.call_count == 2
    mock_blob.download_to_filename.assert_called_once_with("/tmp/fake_dir/input_job123.mp4")
    mock_blob.upload_from_filename.assert_called_once_with("/tmp/fake_dir/output_job123.mp4", content_type="video/mp4")
    
    # Assert ffmpeg execution
    mock_ffmpeg.input.assert_called_once_with("/tmp/fake_dir/input_job123.mp4")
    mock_input.output.assert_called_once()
    mock_overwrite.run.assert_called_once_with(capture_stdout=True, capture_stderr=True)
    
    assert result_uri == "gs://mcr-relay-1772228380-processed-output/processed_job123.mp4"
