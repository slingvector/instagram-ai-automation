"""
Integration tests for PostingController and FirestoreListenerService.
MCR-502/503: Publishing Edge
"""
import pytest
from unittest.mock import patch, MagicMock, call
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from src.publishing_edge.controllers.posting_controller import PostingController


class TestPostingControllerIntegration:
    """Tests PostingController Firestore state transitions."""

    def _make_job_doc(self, status="ready_to_post"):
        doc = MagicMock()
        doc.exists = True
        doc.to_dict.return_value = {
            "status": status,
            "gcs_video_uri": "gs://test-bucket/reels/test.mp4",
            "caption": "Test caption",
            "hashtags": ["#test", "#mcr"],
        }
        return doc

    @patch("src.publishing_edge.controllers.posting_controller.AppiumPostingService")
    @patch("src.publishing_edge.controllers.posting_controller.ADBClient")
    @patch("src.publishing_edge.controllers.posting_controller.storage.Client")
    @patch("src.publishing_edge.controllers.posting_controller.firestore.Client")
    def test_approved_flow_posts_and_updates_status(
        self, mock_fs_cls, mock_gcs_cls, mock_adb_cls, mock_appium_cls
    ):
        """Approved review → share_post called → Firestore status = 'posted'."""
        # Setup Firestore mock
        mock_db = MagicMock()
        mock_fs_cls.return_value = mock_db
        job_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = job_ref
        job_ref.get.return_value = self._make_job_doc()

        # Setup Appium mock — prepare_reel_post succeeds
        mock_appium = MagicMock()
        mock_appium_cls.return_value = mock_appium

        # Setup GCS mock — download succeeds
        mock_gcs = MagicMock()
        mock_gcs_cls.return_value = mock_gcs

        # Setup ADB mock
        mock_adb = MagicMock()
        mock_adb.push_file.return_value = "/sdcard/Download/test.mp4"
        mock_adb_cls.return_value = mock_adb

        controller = PostingController()

        # Simulate human approval: _wait_for_review_decision returns 'approved'
        with patch.object(controller, "_wait_for_review_decision", return_value="approved"), \
             patch.object(controller, "_download_to_device", return_value="/sdcard/Download/test.mp4"):
            controller.execute("test-job-123")

        # Appium prepare and share both called
        mock_appium.prepare_reel_post.assert_called_once()
        mock_appium.share_post.assert_called_once()

        # Firestore updated to 'posted'
        update_calls = [str(c) for c in job_ref.update.call_args_list]
        assert any("posted" in c for c in update_calls)

    @patch("src.publishing_edge.controllers.posting_controller.AppiumPostingService")
    @patch("src.publishing_edge.controllers.posting_controller.ADBClient")
    @patch("src.publishing_edge.controllers.posting_controller.storage.Client")
    @patch("src.publishing_edge.controllers.posting_controller.firestore.Client")
    def test_rejected_flow_cancels_and_updates_status(
        self, mock_fs_cls, mock_gcs_cls, mock_adb_cls, mock_appium_cls
    ):
        """Rejected review → cancel_post called → Firestore status = 'rejected'."""
        mock_db = MagicMock()
        mock_fs_cls.return_value = mock_db
        job_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = job_ref
        job_ref.get.return_value = self._make_job_doc()

        mock_appium = MagicMock()
        mock_appium_cls.return_value = mock_appium
        mock_gcs_cls.return_value = MagicMock()
        mock_adb_cls.return_value = MagicMock()

        controller = PostingController()

        with patch.object(controller, "_wait_for_review_decision", return_value="rejected"), \
             patch.object(controller, "_download_to_device", return_value="/sdcard/Download/test.mp4"):
            controller.execute("test-job-456")

        mock_appium.cancel_post.assert_called_once()
        mock_appium.share_post.assert_not_called()

        update_calls = [str(c) for c in job_ref.update.call_args_list]
        assert any("rejected" in c for c in update_calls)

    @patch("src.publishing_edge.controllers.posting_controller.AppiumPostingService")
    @patch("src.publishing_edge.controllers.posting_controller.ADBClient")
    @patch("src.publishing_edge.controllers.posting_controller.storage.Client")
    @patch("src.publishing_edge.controllers.posting_controller.firestore.Client")
    def test_appium_failure_sets_failed_status(
        self, mock_fs_cls, mock_gcs_cls, mock_adb_cls, mock_appium_cls
    ):
        """Appium crash during staging → Firestore status = 'failed'."""
        mock_db = MagicMock()
        mock_fs_cls.return_value = mock_db
        job_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = job_ref
        job_ref.get.return_value = self._make_job_doc()

        mock_appium = MagicMock()
        mock_appium.prepare_reel_post.side_effect = RuntimeError("Appium session lost")
        mock_appium_cls.return_value = mock_appium
        mock_gcs_cls.return_value = MagicMock()
        mock_adb_cls.return_value = MagicMock()

        controller = PostingController()

        with patch.object(controller, "_download_to_device", return_value="/sdcard/Download/test.mp4"):
            controller.execute("test-job-789")

        update_calls = [str(c) for c in job_ref.update.call_args_list]
        assert any("failed" in c for c in update_calls)
        mock_appium.end_session.assert_called_once()
