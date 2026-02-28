#!/usr/bin/env python3
"""
record_flow.py — Flow Recorder Service
=======================================
Records a screen video, periodic XML UI dumps, and raw touch events
while you manually perform any Instagram flow on your phone.

Recording stops automatically when you close the app.
The session folder is then ready for AI analysis via analyze_flow.py.

Usage:
    python tools/record_flow.py <flow_name>

Example:
    python tools/record_flow.py create_reel
    python tools/record_flow.py add_caption
"""

import os
import sys
import time
import threading
import subprocess
import json
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_PACKAGE = "com.instagram.android"
ADB = "adb"
XML_POLL_INTERVAL = 1.5    # seconds between UI XML snapshots
MAX_RECORD_SECONDS = 300   # 5-minute cap for adb screenrecord
DEVICE_VIDEO_PATH  = "/sdcard/mcr_flow_record.mp4"
DEVICE_XML_PATH    = "/sdcard/mcr_ui_snap.xml"

# ── Shared state ──────────────────────────────────────────────────────────────
stop_flag = threading.Event()


# ── ADB helpers ───────────────────────────────────────────────────────────────

def adb(*args, capture: bool = True, timeout: int = 10) -> str:
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


def is_app_running(package: str) -> bool:
    out = adb("shell", f"pidof {package}", timeout=5)
    return bool(out.strip())


def pull_file(device_path: str, local_path: str) -> bool:
    result = subprocess.run(
        [ADB, "pull", device_path, local_path],
        capture_output=True, timeout=15
    )
    return result.returncode == 0


# ── Worker threads ────────────────────────────────────────────────────────────

def app_monitor_thread():
    """
    Waits for Instagram to open, then waits for it to close.
    Sets stop_flag when the app is closed — ending the session.
    """
    print("⏳  Waiting for Instagram to open...")
    while not stop_flag.is_set():
        if is_app_running(TARGET_PACKAGE):
            break
        time.sleep(1)

    if stop_flag.is_set():
        return

    print("📱  Instagram detected! Perform your flow now.")
    print("    Close Instagram when finished.\n")

    while not stop_flag.is_set():
        if not is_app_running(TARGET_PACKAGE):
            print("\n✅  Instagram closed — stopping session.")
            stop_flag.set()
            return
        time.sleep(1)


def xml_poller_thread(session_dir: Path):
    """
    Every XML_POLL_INTERVAL seconds:
      1. Dumps the current UI tree to device
      2. Pulls it to the session folder with a timestamped filename
    """
    snap_num = 0
    while not stop_flag.is_set():
        try:
            ts = datetime.now().strftime("%H%M%S_%f")[:-3]
            local_xml = session_dir / f"snap_{snap_num:05d}_{ts}.xml"
            adb("shell", "uiautomator", "dump", DEVICE_XML_PATH, timeout=8)
            if pull_file(DEVICE_XML_PATH, str(local_xml)):
                snap_num += 1
                print(f"  📋  XML snapshot #{snap_num:03d} saved", end="\r")
        except Exception:
            pass
        stop_flag.wait(timeout=XML_POLL_INTERVAL)
    
    print(f"\n  📋  Total XML snapshots: {snap_num}")


def touch_logger_thread(session_dir: Path):
    """
    Captures raw touchscreen events from the device via getevent.
    These give exact tap coordinates + timestamps for AI cross-referencing.
    getevent may require USB debugging — failure here is non-fatal.
    """
    log_path = session_dir / "touches.log"
    cmd = [ADB, "shell", "getevent", "-lt"]
    try:
        with open(log_path, "w") as f:
            proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.DEVNULL)
            stop_flag.wait()
            proc.terminate()
            proc.wait(timeout=3)
    except Exception as e:
        # Non-fatal: getevent may not be available without root on some devices
        with open(log_path, "w") as f:
            f.write(f"[touch_logger] Could not capture events: {e}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    flow_name = sys.argv[1] if len(sys.argv) > 1 else "unnamed_flow"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_name = f"{flow_name}_{ts}"
    session_dir = Path("recordings") / session_name
    session_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n🎬  Flow Recorder  —  Session: {session_name}")
    print(f"    Saving to: {session_dir}/\n")

    # Verify device
    if "device" not in adb("devices"):
        print("❌  No ADB device found. Connect your phone and retry.")
        sys.exit(1)

    # Start screen recording on-device
    print(f"🎥  Starting screen recording (max {MAX_RECORD_SECONDS}s)...")
    record_proc = adb_popen(
        "shell", "screenrecord",
        f"--time-limit={MAX_RECORD_SECONDS}",
        DEVICE_VIDEO_PATH
    )

    # Launch worker threads
    threads = [
        threading.Thread(target=app_monitor_thread,   daemon=True),
        threading.Thread(target=xml_poller_thread,    args=(session_dir,), daemon=True),
        threading.Thread(target=touch_logger_thread,  args=(session_dir,), daemon=True),
    ]
    for t in threads:
        t.start()

    # Block until session ends (stop_flag set by app_monitor_thread)
    try:
        stop_flag.wait()
    except KeyboardInterrupt:
        print("\n⚠️   Interrupted by user.")
        stop_flag.set()

    # Give threads time to finish their final snapshot
    print("⏳  Waiting for threads to finish...")
    for t in threads:
        t.join(timeout=5)

    # Stop screen recording
    record_proc.terminate()
    time.sleep(2)   # give device time to flush the MP4

    # Pull video from device
    video_local = session_dir / "screen_recording.mp4"
    print("⬇️   Pulling screen recording from device...")
    if pull_file(DEVICE_VIDEO_PATH, str(video_local)):
        print(f"    ✅  Saved: {video_local}")
    else:
        print("    ⚠️   Could not pull video (may still be on device).")

    # Count artifacts
    xml_files = sorted(session_dir.glob("snap_*.xml"))

    # Save manifest
    manifest = {
        "session_name":  session_name,
        "flow_name":     flow_name,
        "recorded_at":   ts,
        "target_package": TARGET_PACKAGE,
        "xml_snapshots": len(xml_files),
        "files": {
            "video":   "screen_recording.mp4",
            "touches": "touches.log",
        },
        "status": "ready_for_analysis"
    }
    with open(session_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # Summary
    print(f"\n{'─'*55}")
    print(f"📦  Session saved: recordings/{session_name}/")
    print(f"    🎥  Video      : screen_recording.mp4")
    print(f"    📋  XML snaps  : {len(xml_files)} files")
    print(f"    👆  Touches    : touches.log")
    print(f"    📄  Manifest   : manifest.json")
    print(f"{'─'*55}")
    print(f"\n▶️   Next step — run the AI analyzer:")
    print(f"    python tools/analyze_flow.py recordings/{session_name}")
    print()


if __name__ == "__main__":
    main()
