#!/usr/bin/env python3
"""
record_flow.py — Universal App Flow Recorder
=============================================
Records screen video, periodic XML UI dumps, raw touch events, and
**screenshots on every screen change** while you manually perform any
flow on your Android phone.

This is app-agnostic — works with Instagram, LinkedIn, dating apps, or
any Android app.  Recording stops automatically when the target app
leaves the foreground.

Artifacts produced:
  - screen_recording_NNN.mp4  (chained 5-min segments)
  - snap_NNNNN_HHMMSS_mmm.xml  (UI tree on every change)
  - transition_NNN_HHMMSS_mmm.png  (screenshot on change)
  - touches.log  (raw getevent -lt stream)
  - transitions_log.jsonl  (machine-readable transition log)
  - manifest.json  (session metadata)

Usage:
    python tools/record_flow.py <flow_name>
    python tools/record_flow.py <flow_name> --package com.linkedin.android
    python tools/record_flow.py <flow_name> --package auto
"""

import argparse
import atexit
import os
import sys
import time
import threading
import subprocess
import json
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_PACKAGE    = "com.instagram.android"
ADB                = "adb"
XML_POLL_INTERVAL  = 1.5    # seconds between UI polls
MAX_RECORD_SECONDS = 300    # 5-minute cap per adb screenrecord segment
DEVICE_XML_PATH    = "/sdcard/mcr_ui_snap.xml"
DEVICE_SCREEN_PATH = "/sdcard/mcr_trans.png"
VIDEO_PULL_RETRIES = 3
VIDEO_PULL_DELAY   = 2      # seconds between retries
ADB_RECONNECT_MAX  = 3      # max ADB reconnect attempts
ADB_RECONNECT_WAIT = 3      # seconds between reconnect attempts

# ── Shared state ──────────────────────────────────────────────────────────────
stop_flag = threading.Event()
_record_procs     = []       # list of screenrecord Popen handles
_session_dir      = None     # current session directory
_device_video_paths = []     # per-segment device video paths
_target_package   = DEFAULT_PACKAGE


# ── ADB helpers ───────────────────────────────────────────────────────────────

def adb(*args, capture: bool = True, timeout: int = 10) -> str:
    """Run an ADB command and return stdout. Returns '' on any error."""
    cmd = [ADB] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""
    except Exception:
        return ""


def adb_popen(*args) -> subprocess.Popen:
    """Start an ADB command in the background and return the Popen handle."""
    cmd = [ADB] + list(args)
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def is_device_connected() -> bool:
    """Check if an ADB device is currently connected."""
    return "device" in adb("devices", timeout=5)


def is_app_running(package: str) -> bool:
    """Check if the app is currently focused in the foreground."""
    out = adb("shell", "dumpsys", "window", "windows", timeout=5)
    return package in out


def get_foreground_package() -> str:
    """Get the package name of the current foreground app."""
    out = adb("shell", "dumpsys", "window", "windows", timeout=5)
    for line in out.splitlines():
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            # Extract package from patterns like "com.example.app/.Activity"
            for token in line.split():
                if "/" in token and "." in token:
                    pkg = token.split("/")[0]
                    # Clean up leading/trailing braces
                    pkg = pkg.strip("{}")
                    if "." in pkg and len(pkg) > 3:
                        return pkg
    return ""


def pull_file(device_path: str, local_path: str, retries: int = 1, delay: float = 1) -> bool:
    """Pull a file from the device with retry logic."""
    for attempt in range(retries):
        try:
            result = subprocess.run(
                [ADB, "pull", device_path, local_path],
                capture_output=True, timeout=30
            )
            if result.returncode == 0:
                if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                    return True
        except Exception:
            pass
        if attempt < retries - 1:
            time.sleep(delay)
    return False


def capture_screenshot(local_path: str) -> bool:
    """Capture a PNG screenshot from the device."""
    try:
        adb("shell", "screencap", "-p", DEVICE_SCREEN_PATH, timeout=10)
        return pull_file(DEVICE_SCREEN_PATH, local_path)
    except Exception:
        return False


# ── XML Fingerprinting ───────────────────────────────────────────────────────

def xml_fingerprint(xml_path: Path) -> str:
    """
    Compute a content-based fingerprint of the XML UI tree.
    Returns a hash of all visible text + content-desc + resource-id values.
    Two identical screens will produce the same fingerprint.
    """
    try:
        tree = ET.parse(str(xml_path))
        parts = []
        for node in tree.getroot().iter():
            text = node.attrib.get("text", "").strip()
            desc = node.attrib.get("content-desc", "").strip()
            rid  = node.attrib.get("resource-id", "").strip()
            bounds = node.attrib.get("bounds", "")
            if text or desc or rid:
                parts.append(f"{text}|{desc}|{rid}|{bounds}")
        content = "\n".join(parts)
        return hashlib.md5(content.encode()).hexdigest()[:12]
    except Exception:
        return ""


def xml_summary(xml_path: Path, max_items: int = 8) -> str:
    """Return a short human-readable summary of the screen content."""
    try:
        tree = ET.parse(str(xml_path))
        texts = []
        for node in tree.getroot().iter():
            text = node.attrib.get("text", "").strip()
            desc = node.attrib.get("content-desc", "").strip()
            label = text or desc
            if label and label not in texts:
                texts.append(label)
            if len(texts) >= max_items:
                break
        return " | ".join(t[:30] for t in texts)
    except Exception:
        return "(unparseable)"


# ── Cleanup ───────────────────────────────────────────────────────────────────

def _cleanup():
    """Atexit handler: ensures videos are pulled and manifest is written."""
    global _record_procs, _session_dir, _device_video_paths

    for proc in _record_procs:
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    if _session_dir is None:
        return

    time.sleep(2)

    # Pull any video segments not yet pulled
    for i, device_path in enumerate(_device_video_paths):
        local = _session_dir / f"screen_recording_{i:03d}.mp4"
        if not local.exists():
            print(f"\n⬇️   Pulling video segment {i} (cleanup)...")
            pull_file(device_path, str(local), retries=VIDEO_PULL_RETRIES, delay=VIDEO_PULL_DELAY)

    manifest_path = _session_dir / "manifest.json"
    if not manifest_path.exists():
        xml_files = sorted(_session_dir.glob("snap_*.xml"))
        screenshots = sorted(_session_dir.glob("transition_*.png"))
        manifest = {
            "session_name":  _session_dir.name,
            "flow_name":     "unknown",
            "recorded_at":   datetime.now().strftime("%Y%m%d_%H%M%S"),
            "target_package": _target_package,
            "xml_snapshots": len(xml_files),
            "screenshots":   len(screenshots),
            "files": {
                "touches": "touches.log",
                "transitions_log": "transitions_log.jsonl",
            },
            "status": "partial_cleanup"
        }
        try:
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)
        except Exception:
            pass


# ── Worker threads ────────────────────────────────────────────────────────────

def app_monitor_thread():
    """
    Waits for the target app to open, then waits for it to close.
    Sets stop_flag when the app leaves foreground — ending the session.
    """
    app_name = _target_package.split(".")[-1] if "." in _target_package else _target_package

    print(f"⏳  Waiting for {app_name} to open...")
    while not stop_flag.is_set():
        if is_app_running(_target_package):
            break
        stop_flag.wait(timeout=1)

    if stop_flag.is_set():
        return

    print(f"📱  {app_name} detected! Perform your flow now.")
    print(f"    Close {app_name} when finished.\n")

    # Debounce: require 3 consecutive checks where app is NOT foreground
    # to avoid false positives from brief overlay dialogs
    gone_count = 0
    while not stop_flag.is_set():
        if not is_app_running(_target_package):
            gone_count += 1
            if gone_count >= 3:
                print(f"\n✅  {app_name} closed — stopping session.")
                stop_flag.set()
                return
        else:
            gone_count = 0
        stop_flag.wait(timeout=1)


def xml_poller_thread(session_dir: Path):
    """
    Smart XML poller with screen-change detection:
      1. Dumps the current UI tree every XML_POLL_INTERVAL seconds
      2. Computes a content fingerprint of each dump
      3. If fingerprint changed → saves XML + captures a PNG screenshot
      4. If unchanged → skips saving (no duplicate XML files)
      5. Writes transition events to transitions_log.jsonl
    """
    snap_num = 0
    transition_num = 0
    prev_fingerprint = ""
    transitions_log = session_dir / "transitions_log.jsonl"
    consecutive_adb_fails = 0

    while not stop_flag.is_set():
        try:
            ts = datetime.now().strftime("%H%M%S_%f")[:-3]
            tmp_xml = session_dir / f"_tmp_snap.xml"

            # Dump UI tree to device, pull to local temp
            dump_result = adb("shell", "uiautomator", "dump", DEVICE_XML_PATH, timeout=8)
            if not dump_result or "error" in dump_result.lower():
                consecutive_adb_fails += 1
                if consecutive_adb_fails >= ADB_RECONNECT_MAX:
                    print(f"\n⚠️   ADB unresponsive ({consecutive_adb_fails} failures). Attempting reconnect...")
                    adb("reconnect", timeout=5)
                    time.sleep(ADB_RECONNECT_WAIT)
                    consecutive_adb_fails = 0
                stop_flag.wait(timeout=XML_POLL_INTERVAL)
                continue

            if not pull_file(DEVICE_XML_PATH, str(tmp_xml)):
                stop_flag.wait(timeout=XML_POLL_INTERVAL)
                continue

            consecutive_adb_fails = 0  # reset on success

            # Compute fingerprint
            fp = xml_fingerprint(tmp_xml)

            if fp == prev_fingerprint and fp != "":
                # Screen unchanged — skip saving duplicate
                tmp_xml.unlink(missing_ok=True)
                stop_flag.wait(timeout=XML_POLL_INTERVAL)
                continue

            # ── Screen changed! Save XML + screenshot ────────────────────
            local_xml = session_dir / f"snap_{snap_num:05d}_{ts}.xml"
            tmp_xml.rename(local_xml)
            snap_num += 1

            # Capture screenshot on every transition
            screenshot_name = f"transition_{transition_num:03d}_{ts}.png"
            screenshot_path = session_dir / screenshot_name
            screenshot_ok = capture_screenshot(str(screenshot_path))

            # Get human-readable summary
            summary = xml_summary(local_xml)

            # Write transition event
            event = {
                "transition": transition_num,
                "snap_index": snap_num - 1,
                "timestamp": datetime.now().isoformat(),
                "xml_file": local_xml.name,
                "screenshot": screenshot_name if screenshot_ok else None,
                "fingerprint": fp,
                "prev_fingerprint": prev_fingerprint,
                "summary": summary,
            }
            with open(transitions_log, "a") as f:
                f.write(json.dumps(event) + "\n")

            # Console output
            sc_icon = "📸" if screenshot_ok else "📋"
            print(f"  {sc_icon}  Transition #{transition_num:03d} (snap {snap_num:03d}): {summary[:60]}", end="\r\n")

            transition_num += 1
            prev_fingerprint = fp

        except Exception as e:
            # Non-fatal — log and continue
            try:
                with open(session_dir / "errors.log", "a") as f:
                    f.write(f"[{datetime.now().isoformat()}] xml_poller: {e}\n")
            except Exception:
                pass

        stop_flag.wait(timeout=XML_POLL_INTERVAL)

    # Cleanup temp file
    tmp_file = session_dir / "_tmp_snap.xml"
    tmp_file.unlink(missing_ok=True)

    print(f"\n  📋  Total: {snap_num} XML snapshots, {transition_num} transitions")


def touch_logger_thread(session_dir: Path):
    """
    Captures raw touchscreen events via getevent -lt.
    Auto-restarts if the getevent process dies unexpectedly.
    """
    log_path = session_dir / "touches.log"

    # Sync Marker: Host Time ↔ Device Uptime for analysis alignment
    uptime = adb("shell", "cat", "/proc/uptime").split()[0] if adb("shell", "cat", "/proc/uptime") else "0"
    host_ts = datetime.now().isoformat()

    cmd = [ADB, "shell", "getevent", "-lt"]
    restart_count = 0
    max_restarts = 5

    while not stop_flag.is_set() and restart_count < max_restarts:
        try:
            with open(log_path, "a" if restart_count > 0 else "w") as f:
                if restart_count == 0:
                    f.write(f"# SYNC_MARKER|HOST:{host_ts}|UPTIME:{uptime}\n")
                else:
                    f.write(f"# RESTART_{restart_count}|HOST:{datetime.now().isoformat()}\n")
                f.flush()

                proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.DEVNULL)

                # Poll until stop_flag is set or process dies
                while not stop_flag.is_set():
                    ret = proc.poll()
                    if ret is not None:
                        # Process died — will restart
                        break
                    stop_flag.wait(timeout=2)

                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()

                if stop_flag.is_set():
                    return

                # Process died unexpectedly — restart
                restart_count += 1
                print(f"\n  ⚠️   getevent died. Restarting ({restart_count}/{max_restarts})...")
                time.sleep(1)

        except Exception as e:
            with open(log_path, "a") as f:
                f.write(f"# ERROR: {e}\n")
            restart_count += 1
            time.sleep(1)


def video_recorder_thread():
    """
    Chains multiple 5-minute screenrecord segments.
    Android limits screenrecord to ~180s or 300s depending on device.
    This thread starts a new segment when the previous one ends.
    """
    global _record_procs, _device_video_paths

    segment = 0
    while not stop_flag.is_set():
        session_name = _session_dir.name if _session_dir else "unknown"
        device_path = f"/sdcard/mcr_flow_{session_name}_{segment:03d}.mp4"
        _device_video_paths.append(device_path)

        proc = adb_popen(
            "shell", "screenrecord",
            f"--time-limit={MAX_RECORD_SECONDS}",
            device_path
        )
        _record_procs.append(proc)

        # Wait for segment to finish (time limit) or stop_flag
        start = time.time()
        while not stop_flag.is_set():
            ret = proc.poll()
            if ret is not None:
                # Segment finished (time limit reached)
                break
            elapsed = time.time() - start
            if elapsed > MAX_RECORD_SECONDS + 5:
                # Safety timeout
                break
            stop_flag.wait(timeout=2)

        if stop_flag.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            return

        segment += 1
        print(f"\n  🎥  Video segment {segment} complete. Starting segment {segment + 1}...")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global _record_procs, _session_dir, _device_video_paths, _target_package

    parser = argparse.ArgumentParser(
        description="Record any Android app flow (screen video + XML UI dumps + screenshots + touch events).",
        epilog=(
            "Examples:\n"
            "  python tools/record_flow.py create_reel\n"
            "  python tools/record_flow.py apply_job --package com.linkedin.android\n"
            "  python tools/record_flow.py explore --package auto\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "flow_name",
        help="Short name for this flow (e.g. create_reel, copy_link, swipe_test)"
    )
    parser.add_argument(
        "--package", "-p",
        default=DEFAULT_PACKAGE,
        help=f"Target app package (default: {DEFAULT_PACKAGE}). Use 'auto' to detect foreground app."
    )
    args = parser.parse_args()

    # Resolve target package
    _target_package = args.package
    if _target_package == "auto":
        print("🔍  Auto-detecting foreground app...")
        detected = get_foreground_package()
        if detected:
            _target_package = detected
            print(f"    Found: {_target_package}")
        else:
            print("❌  Could not detect foreground app. Specify --package explicitly.")
            sys.exit(1)

    flow_name = args.flow_name
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_name = f"{flow_name}_{ts}"
    session_dir = Path("recordings") / session_name
    session_dir.mkdir(parents=True, exist_ok=True)

    _session_dir = session_dir
    atexit.register(_cleanup)

    app_short = _target_package.split(".")[-1] if "." in _target_package else _target_package
    print(f"\n🎬  Universal Flow Recorder  —  {session_name}")
    print(f"    Target: {_target_package}")
    print(f"    Saving: {session_dir}/\n")

    # Verify device
    if not is_device_connected():
        print("❌  No ADB device found. Connect your phone and retry.")
        sys.exit(1)

    # Launch worker threads
    threads = [
        threading.Thread(target=app_monitor_thread,      daemon=True, name="app_monitor"),
        threading.Thread(target=xml_poller_thread,       args=(session_dir,), daemon=True, name="xml_poller"),
        threading.Thread(target=touch_logger_thread,     args=(session_dir,), daemon=True, name="touch_logger"),
        threading.Thread(target=video_recorder_thread,   daemon=True, name="video_recorder"),
    ]
    for t in threads:
        t.start()

    # Block until session ends
    try:
        stop_flag.wait()
    except KeyboardInterrupt:
        print("\n⚠️   Interrupted by user.")
        stop_flag.set()

    # Give threads time to finish
    print("⏳  Waiting for threads to finish...")
    for t in threads:
        t.join(timeout=5)

    # Stop all video recorders
    for proc in _record_procs:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    time.sleep(2)  # give device time to flush

    # Pull video segments
    for i, device_path in enumerate(_device_video_paths):
        local = session_dir / f"screen_recording_{i:03d}.mp4"
        if not local.exists():
            print(f"⬇️   Pulling video segment {i}...")
            if pull_file(device_path, str(local), retries=VIDEO_PULL_RETRIES, delay=VIDEO_PULL_DELAY):
                print(f"    ✅  Saved: {local}")
            else:
                print(f"    ⚠️   Could not pull segment {i}.")

    # Count artifacts
    xml_files = sorted(session_dir.glob("snap_*.xml"))
    screenshots = sorted(session_dir.glob("transition_*.png"))
    video_files = sorted(session_dir.glob("screen_recording_*.mp4"))

    # Manifest
    manifest = {
        "session_name":  session_name,
        "flow_name":     flow_name,
        "recorded_at":   ts,
        "target_package": _target_package,
        "xml_snapshots": len(xml_files),
        "screenshots":   len(screenshots),
        "video_segments": len(video_files),
        "files": {
            "videos":          [f.name for f in video_files],
            "touches":         "touches.log",
            "transitions_log": "transitions_log.jsonl",
        },
        "has_video": any(f.exists() for f in video_files),
        "status": "ready_for_analysis"
    }
    with open(session_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # Clear handled procs so atexit doesn't re-terminate
    _record_procs = []

    # Summary
    video_count = len(video_files)
    video_status = f"✅ {video_count} segment{'s' if video_count != 1 else ''}" if video_count else "⚠️  missing"
    print(f"\n{'─'*60}")
    print(f"📦  Session saved: recordings/{session_name}/")
    print(f"    🎥  Video        : {video_status}")
    print(f"    📋  XML snaps    : {len(xml_files)} unique screens")
    print(f"    📸  Screenshots  : {len(screenshots)} transitions")
    print(f"    👆  Touches      : touches.log")
    print(f"    📄  Transitions  : transitions_log.jsonl")
    print(f"    📄  Manifest     : manifest.json")
    print(f"{'─'*60}")
    print(f"\n▶️   Next — run the analyzer:")
    print(f"    python tools/analyze_flow.py recordings/{session_name}")
    print()


if __name__ == "__main__":
    main()
