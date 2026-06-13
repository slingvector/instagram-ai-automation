"""
Unit tests for analyze_flow.py — touch parsing, timestamp extraction, and offset logic.
These tests run without a device by using mock data.
"""
import pytest
import sys
import os
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from tools.analyze_flow import (
    parse_touches,
    _parse_xml_timestamp,
    get_uptime_to_host_offset,
    xml_fingerprint,
    extract_interactive_elements,
)


# ── Sample getevent -lt data ─────────────────────────────────────────────────

SAMPLE_TOUCH_LOG = """# SYNC_MARKER|HOST:2026-03-08T22:15:46.641330|UPTIME:2601734.03
[  2601740.100000] /dev/input/event8: EV_KEY       BTN_TOUCH            DOWN
[  2601740.100000] /dev/input/event8: EV_ABS       ABS_MT_POSITION_X    00000800
[  2601740.100000] /dev/input/event8: EV_ABS       ABS_MT_POSITION_Y    00001000
[  2601740.100000] /dev/input/event8: EV_SYN       SYN_REPORT           00000000
[  2601740.200000] /dev/input/event8: EV_KEY       BTN_TOUCH            UP
[  2601740.200000] /dev/input/event8: EV_SYN       SYN_REPORT           00000000
[  2601742.300000] /dev/input/event8: EV_KEY       BTN_TOUCH            DOWN
[  2601742.300000] /dev/input/event8: EV_ABS       ABS_MT_POSITION_X    00000100
[  2601742.300000] /dev/input/event8: EV_ABS       ABS_MT_POSITION_Y    00000100
[  2601742.300000] /dev/input/event8: EV_SYN       SYN_REPORT           00000000
[  2601742.400000] /dev/input/event8: EV_ABS       ABS_MT_POSITION_X    00000f00
[  2601742.400000] /dev/input/event8: EV_ABS       ABS_MT_POSITION_Y    00000f00
[  2601742.400000] /dev/input/event8: EV_SYN       SYN_REPORT           00000000
[  2601742.500000] /dev/input/event8: EV_KEY       BTN_TOUCH            UP
[  2601742.500000] /dev/input/event8: EV_SYN       SYN_REPORT           00000000
"""

SAMPLE_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node text="Home" resource-id="com.instagram.android:id/feed_tab"
        class="android.widget.FrameLayout" content-desc="Home"
        bounds="[0,2868][288,3060]" clickable="true" />
  <node text="" resource-id="com.instagram.android:id/media_option_button"
        class="android.widget.ImageView" content-desc="More actions for this post"
        bounds="[1264,218][1440,410]" clickable="true" />
  <node text="Follow" resource-id="com.instagram.android:id/inline_follow_button"
        class="android.widget.Button" content-desc="Follow VLTRA Society"
        bounds="[931,246][1264,381]" clickable="true" />
</hierarchy>
"""


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestParseTouches:
    """Tests for the getevent -lt touch parser."""

    def test_parses_tap_and_swipe(self, tmp_path):
        log_file = tmp_path / "touches.log"
        log_file.write_text(SAMPLE_TOUCH_LOG)

        gestures = parse_touches(log_file)

        assert len(gestures) == 2

        # First gesture: single point tap
        tap = gestures[0]
        assert tap["type"] == "tap"
        assert tap["start_x"] == tap["end_x"]
        assert tap["start_y"] == tap["end_y"]
        assert tap["duration"] == pytest.approx(0.1, abs=0.01)

        # Second gesture: large movement = swipe
        swipe = gestures[1]
        assert swipe["type"] == "swipe"
        assert swipe["dist"] > 60
        assert swipe["points"] >= 2

    def test_empty_file_returns_empty(self, tmp_path):
        log_file = tmp_path / "touches.log"
        log_file.write_text("# SYNC_MARKER|HOST:2026-03-08T22:15:46|UPTIME:123\n")
        
        gestures = parse_touches(log_file)
        assert gestures == []

    def test_missing_file_returns_empty(self, tmp_path):
        gestures = parse_touches(tmp_path / "nonexistent.log")
        assert gestures == []

    def test_gesture_has_duration_and_points(self, tmp_path):
        log_file = tmp_path / "touches.log"
        log_file.write_text(SAMPLE_TOUCH_LOG)

        gestures = parse_touches(log_file)
        for g in gestures:
            assert "duration" in g
            assert "points" in g
            assert g["duration"] >= 0
            assert g["points"] >= 1


class TestParseXmlTimestamp:
    """Tests for extracting wall-clock time from XML filenames."""

    def test_parses_filename_with_date(self):
        path = Path("/fake/snap_00148_222446_853.xml")
        ts = _parse_xml_timestamp(path, "20260308")
        
        dt = datetime.fromtimestamp(ts)
        assert dt.hour == 22
        assert dt.minute == 24
        assert dt.second == 46
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 8

    def test_parses_filename_without_date_falls_back(self):
        path = Path("/fake/snap_00000_120000_000.xml")
        ts = _parse_xml_timestamp(path, "")
        
        dt = datetime.fromtimestamp(ts)
        assert dt.hour == 12
        assert dt.minute == 0
        assert dt.second == 0

    def test_bad_filename_falls_back_to_mtime(self, tmp_path):
        bad_file = tmp_path / "not_a_snap.xml"
        bad_file.write_text("<xml/>")
        
        ts = _parse_xml_timestamp(bad_file, "20260308")
        # Should return mtime instead of crashing
        assert ts > 0


class TestUptimeOffset:
    """Tests for SYNC_MARKER validation and offset fallback logic."""

    def test_sync_marker_valid_when_uptimes_match(self, tmp_path):
        log = tmp_path / "touches.log"
        log.write_text("# SYNC_MARKER|HOST:2026-03-08T22:15:46.641330|UPTIME:2601734.03\n")
        
        # Gestures are near the SYNC_MARKER uptime
        offset = get_uptime_to_host_offset(
            tmp_path,
            first_uptime=2601730.0,
            last_uptime=2601740.0,
            session_date="20260308"
        )
        
        # SYNC_MARKER should be trusted — offset = host_ts - sync_uptime
        host_ts = datetime.fromisoformat("2026-03-08T22:15:46.641330").timestamp()
        expected = host_ts - 2601734.03
        assert offset == pytest.approx(expected, abs=0.1)

    def test_sync_marker_rejected_on_reboot(self, tmp_path):
        log = tmp_path / "touches.log"
        log.write_text("# SYNC_MARKER|HOST:2026-03-08T22:15:46.641330|UPTIME:2601734.03\n")
        
        # Create a fake XML file so the fallback has something to work with
        xml = tmp_path / "snap_00000_221546_000.xml"
        xml.write_text("<xml/>")
        xml2 = tmp_path / "snap_00001_221600_000.xml"
        xml2.write_text("<xml/>")
        
        # Gestures have uptimes ~1.3M (far from SYNC_MARKER's 2.6M = rebooted)
        offset = get_uptime_to_host_offset(
            tmp_path,
            first_uptime=1296936.0,
            last_uptime=1299088.0,
            session_date="20260308"
        )
        
        # Should NOT use SYNC_MARKER. Offset should use XML alignment fallback.
        host_ts = datetime.fromisoformat("2026-03-08T22:15:46.641330").timestamp()
        sync_offset = host_ts - 2601734.03
        assert offset != pytest.approx(sync_offset, abs=100)


class TestXmlHelpers:
    """Tests for XML parsing helpers."""

    def test_extract_interactive_elements(self, tmp_path):
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(SAMPLE_XML)
        
        elements = extract_interactive_elements(xml_file)
        
        assert len(elements) >= 3
        texts = [e["text"] for e in elements]
        assert "Home" in texts
        assert "More actions for this post" in texts
        assert "Follow" in texts

    def test_xml_fingerprint(self, tmp_path):
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(SAMPLE_XML)
        
        fp = xml_fingerprint(xml_file)
        assert "Home" in fp
        assert "|" in fp  # fingerprint joins with " | "

    def test_fingerprint_empty_xml(self, tmp_path):
        xml_file = tmp_path / "empty.xml"
        xml_file.write_text('<?xml version="1.0"?><hierarchy/>')
        
        fp = xml_fingerprint(xml_file)
        assert fp == ""
