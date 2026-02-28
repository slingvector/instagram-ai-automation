"""
Unit tests for ADBClient and AppiumPostingService.
MCR-502: Instagram Reel Posting Script
"""
import pytest
from unittest.mock import patch, MagicMock, call
import subprocess
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from src.publishing_edge.services.adb_client import ADBClient


class TestADBClient:
    """Tests for ADBClient — verifies correct ADB commands are issued."""

    @patch("src.publishing_edge.services.adb_client.subprocess.run")
    def test_wake_screen_sends_correct_keycodes(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        client = ADBClient(device_udid="TEST_DEVICE")

        client.wake_screen()

        calls = [str(c) for c in mock_run.call_args_list]
        assert any("KEYCODE_WAKEUP" in c for c in calls)
        assert any("KEYCODE_MENU" in c for c in calls)

    @patch("src.publishing_edge.services.adb_client.subprocess.run")
    def test_launch_instagram_uses_monkey(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        client = ADBClient()

        client.launch_instagram("com.instagram.android")

        cmd_args = mock_run.call_args[0][0]
        assert "monkey" in cmd_args
        assert "com.instagram.android" in cmd_args

    @patch("src.publishing_edge.services.adb_client.subprocess.run")
    def test_push_file_raises_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Permission denied")
        client = ADBClient()

        with pytest.raises(RuntimeError, match="ADB push failed"):
            client.push_file("/tmp/test.mp4", "/sdcard/Download/")

    @patch("src.publishing_edge.services.adb_client.subprocess.run")
    def test_list_devices_parses_output(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="List of devices attached\nABC123\tdevice\nXYZ789\tdevice",
            stderr=""
        )
        client = ADBClient()
        devices = client.list_devices()
        assert "ABC123" in devices
        assert "XYZ789" in devices

    @patch("src.publishing_edge.services.adb_client.subprocess.run")
    def test_tap_calls_adb_input_tap(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        client = ADBClient()
        client.tap(540, 1200)
        cmd_args = mock_run.call_args[0][0]
        assert "540" in cmd_args
        assert "1200" in cmd_args
        assert "tap" in cmd_args

    @patch("src.publishing_edge.services.adb_client.subprocess.run")
    def test_device_udid_adds_s_flag(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        client = ADBClient(device_udid="emulator-5554")

        client.press_home()

        cmd = mock_run.call_args[0][0]
        assert "-s" in cmd
        assert "emulator-5554" in cmd
