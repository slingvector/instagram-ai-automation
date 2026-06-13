#!/usr/bin/env python3
"""
analyze_flow.py — AI Flow Analyzer
====================================
Reads a recording session produced by record_flow.py and uses Gemini Vision
to understand what happened on screen at each step. Outputs:

  - transitions.json  : detected screen changes with touch correlation
  - flow_summary.json : structured step-by-step description
  - generated_steps.py: Python code stub for appium_posting_service.py

Usage:
    python tools/analyze_flow.py recordings/<session_folder>
    python tools/analyze_flow.py recordings/<session_folder> --touches-only

Example:
    python tools/analyze_flow.py recordings/create_reel_20260228_191500

Requirements:
    pip install google-generativeai pillow
    GOOGLE_APPLICATION_CREDENTIALS must point to your GCP service account key
    OR set GEMINI_API_KEY in .env
"""

import argparse
import sys
import os
import json
import math
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Optional AI imports ───────────────────────────────────────────────────────
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# ── Config ────────────────────────────────────────────────────────────────────
# Max seconds between a gesture and a snapshot to consider them correlated.
# A gesture must occur BEFORE the snapshot (with a small lag allowance).
GESTURE_MATCH_WINDOW_BEFORE = 5.0   # gesture can be up to 5s before snapshot
GESTURE_MATCH_WINDOW_AFTER  = 1.5   # or up to 1.5s after (async dump lag)

# Device screen dimensions for coordinate scaling
DEVICE_WIDTH  = 1440
DEVICE_HEIGHT = 3120
RAW_MAX       = 4095   # typical ABS_MT max for touchscreens

# Minimum pixel distance to classify a gesture as a swipe vs tap
SWIPE_THRESHOLD = 60


# ── Touch Parsing ─────────────────────────────────────────────────────────────

def parse_touches(log_path: Path) -> list[dict]:
    """
    Parses getevent -lt log to extract tap/swipe events.
    
    Uses a state-machine approach:
      - BTN_TOUCH DOWN starts a new gesture path
      - ABS_MT_POSITION_X/Y updates accumulate into the path
      - SYN_REPORT commits the current (x,y) as a path point
      - BTN_TOUCH UP finalizes the gesture
    
    Returns a list of gesture dicts with:
      uptime, end_uptime, start_x, start_y, end_x, end_y, dist, type
    """
    if not log_path.exists():
        return []
        
    with open(log_path, "r") as f:
        lines = f.readlines()
        
    gestures = []
    
    SCALE_X = DEVICE_WIDTH / RAW_MAX
    SCALE_Y = DEVICE_HEIGHT / RAW_MAX
    
    # Regex for getevent -lt output:
    # [  1297069.274607] /dev/input/event10: EV_ABS  ABS_MT_POSITION_X  00000a5f
    # [  1297063.123456] /dev/input/event8:  EV_KEY  BTN_TOUCH          DOWN
    pattern = re.compile(
        r"\[\s*([\d\.]+)\s*\]\s+.*:\s+(\w+)\s+(\w+)\s+([0-9a-fA-F\w]+)"
    )
    
    curr_x, curr_y = None, None
    pending_x, pending_y = None, None  # staged coords before SYN_REPORT
    is_down = False
    current_gesture = {"uptime": 0.0, "path": []}

    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        
        ts_str, etype, ecode, evalue = match.group(1, 2, 3, 4)
        ts = float(ts_str)
        
        # ── Finger down/up ──
        if etype == "EV_KEY" and ecode == "BTN_TOUCH":
            is_press = (evalue == "DOWN")
            if not is_press:
                try:
                    is_press = int(evalue, 16) == 1
                except ValueError:
                    is_press = False
            
            if is_press:
                # New gesture starts
                is_down = True
                current_gesture = {"uptime": ts, "path": []}
                pending_x, pending_y = None, None
            else:
                # Gesture ends — commit any staged final point
                if is_down and pending_x is not None and pending_y is not None:
                    current_gesture["path"].append((pending_x, pending_y))
                
                if is_down and len(current_gesture["path"]) > 0:
                    start = current_gesture["path"][0]
                    end = current_gesture["path"][-1]
                    dist = math.sqrt(
                        (end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2
                    )
                    gestures.append({
                        "uptime":   current_gesture["uptime"],
                        "end_uptime": ts,
                        "start_x":  int(start[0]),
                        "start_y":  int(start[1]),
                        "end_x":    int(end[0]),
                        "end_y":    int(end[1]),
                        "dist":     int(dist),
                        "type":     "swipe" if dist > SWIPE_THRESHOLD else "tap",
                        "duration": round(ts - current_gesture["uptime"], 3),
                        "points":   len(current_gesture["path"])
                    })
                is_down = False
                pending_x, pending_y = None, None
        
        # ── Coordinate updates ──
        elif etype == "EV_ABS":
            if ecode in ("ABS_MT_POSITION_X", "0035"):
                pending_x = int(evalue, 16) * SCALE_X
            elif ecode in ("ABS_MT_POSITION_Y", "0036"):
                pending_y = int(evalue, 16) * SCALE_Y
        
        # ── SYN_REPORT: commit the staged coordinate pair ──
        elif etype == "EV_SYN" and ecode == "SYN_REPORT":
            if is_down:
                # Use pending if available, else carry forward last known
                x = pending_x if pending_x is not None else curr_x
                y = pending_y if pending_y is not None else curr_y
                if x is not None and y is not None:
                    current_gesture["path"].append((x, y))
                    curr_x, curr_y = x, y
                pending_x, pending_y = None, None

    if gestures:
        taps = sum(1 for g in gestures if g["type"] == "tap")
        swipes = sum(1 for g in gestures if g["type"] == "swipe")
        print(f"  ✅  Parsed {len(gestures)} gestures ({taps} taps, {swipes} swipes)")
    else:
        print("  ⚠️   No gestures parsed from log.")
        
    return gestures


def get_uptime_to_host_offset(
    session_dir: Path,
    first_uptime: float,
    last_uptime: float,
    session_date: str = ""
) -> float:
    """
    Estimates the offset to sync kernel uptime to host wall-clock time.
    
    The offset satisfies: host_time = uptime + offset
    
    Priority:
      1. SYNC_MARKER (if its uptime is consistent with gesture uptimes)
      2. XML filename timestamps aligned with gesture time range
      3. File mtime heuristic
    """
    log_path = session_dir / "touches.log"
    if not log_path.exists():
        return 0
    
    sync_uptime = None
    sync_host_ts = None
        
    # Try SYNC_MARKER
    try:
        with open(log_path, "r") as f:
            first_line = f.readline()
            if first_line.startswith("# SYNC_MARKER"):
                parts = first_line.strip().split("|")
                host_str = parts[1].split("HOST:")[1]
                uptime_str = parts[2].split("UPTIME:")[1]
                
                sync_host_ts = datetime.fromisoformat(host_str).timestamp()
                sync_uptime = float(uptime_str)
    except Exception:
        pass
    
    # Validate SYNC_MARKER: its uptime should be close to gesture uptimes
    # (within 10% or 1 hour, whichever is larger)
    if sync_uptime is not None and sync_host_ts is not None:
        uptime_gap = abs(sync_uptime - (first_uptime + last_uptime) / 2)
        gesture_span = last_uptime - first_uptime
        tolerance = max(gesture_span * 0.1, 3600)  # 10% of span or 1 hour
        
        if uptime_gap <= tolerance:
            offset = sync_host_ts - sync_uptime
            print(f"  🔗  Sync via SYNC_MARKER (offset: {offset:.2f}s)")
            return offset
        else:
            print(f"  ⚠️   SYNC_MARKER uptime ({sync_uptime:.0f}) too far from "
                  f"gesture uptimes ({first_uptime:.0f}–{last_uptime:.0f}). "
                  f"Device may have rebooted. Using fallback.")
    
    # Strategy 2: Align gesture range midpoint with XML timestamp range midpoint
    xml_files = sorted(session_dir.glob("snap_*.xml"))
    if xml_files and first_uptime > 0:
        first_xml_ts = _parse_xml_timestamp(xml_files[0], session_date)
        last_xml_ts = _parse_xml_timestamp(xml_files[-1], session_date)
        
        xml_mid = (first_xml_ts + last_xml_ts) / 2
        gesture_mid = (first_uptime + last_uptime) / 2
        
        offset = xml_mid - gesture_mid
        print(f"  🔗  Sync via XML filename alignment (offset: {offset:.2f}s)")
        return offset
    
    # Strategy 3: File mtime fallback
    host_mtime = log_path.stat().st_mtime
    offset = host_mtime - last_uptime
    print(f"  🔗  Sync via mtime fallback (offset: {offset:.2f}s)")
    return offset


# ── XML Helpers ───────────────────────────────────────────────────────────────

def extract_interactive_elements(xml_path: Path) -> list[dict]:
    """
    Parses an XML UI dump and extracts all interactive/visible elements
    with their text, content-desc, class, and bounds.
    """
    elements = []
    try:
        tree = ET.parse(xml_path)
        for node in tree.getroot().iter():
            text        = node.attrib.get("text", "").strip()
            desc        = node.attrib.get("content-desc", "").strip()
            cls         = node.attrib.get("class", "").split(".")[-1]
            clickable   = node.attrib.get("clickable", "false") == "true"
            bounds      = node.attrib.get("bounds", "")
            resource_id = node.attrib.get("resource-id", "")

            if (text or desc) and bounds:
                elements.append({
                    "text":   text or desc,
                    "class":  cls,
                    "bounds": bounds,
                    "clickable": clickable,
                    "resource_id": resource_id
                })
    except Exception:
        pass
    return elements


def xml_fingerprint(xml_path: Path) -> str:
    """Return a short fingerprint of identifiable text on screen."""
    elements = extract_interactive_elements(xml_path)
    texts = [e["text"] for e in elements if e["text"]][:10]
    return " | ".join(texts)


def _parse_xml_timestamp(xml_path: Path, session_date: str = "") -> float:
    """
    Extract host wall-clock time from the XML filename.
    
    Filenames follow: snap_00001_223450_710.xml  →  22:34:50.710
    Combined with session_date (e.g. '20260308') to get full timestamp.
    Falls back to mtime if parsing fails.
    """
    try:
        parts = xml_path.stem.split("_")
        # parts: ['snap', '00001', '223450', '710']
        time_str = parts[2]   # '223450'
        ms_str = parts[3]     # '710'
        
        h, m, s = int(time_str[:2]), int(time_str[2:4]), int(time_str[4:6])
        ms = int(ms_str)
        
        if session_date and len(session_date) == 8:
            year  = int(session_date[:4])
            month = int(session_date[4:6])
            day   = int(session_date[6:8])
        else:
            now = datetime.now()
            year, month, day = now.year, now.month, now.day
        
        dt = datetime(year, month, day, h, m, s, ms * 1000)
        return dt.timestamp()
    except Exception:
        return xml_path.stat().st_mtime


def load_transitions_log(session_dir: Path) -> list[dict]:
    """Load pre-computed transitions from transitions_log.jsonl if available."""
    log_path = session_dir / "transitions_log.jsonl"
    if not log_path.exists():
        return []
    transitions = []
    try:
        with open(log_path, "r") as f:
            for line in f:
                if line.strip():
                    transitions.append(json.loads(line))
    except Exception as e:
        print(f"  ⚠️  Error parsing transitions_log.jsonl: {e}")
    return transitions


def detect_screen_transitions(
    session_dir: Path,
    xml_files: list[Path],
    gestures: list[dict],
    offset: float,
    session_date: str = ""
) -> list[dict]:
    """
    Compare consecutive XML snapshots and correlate them with physical gestures.
    
    For each new screen state, find the CLOSEST gesture that happened within
    the match window. Each gesture is used at most once (consumed on match).
    """
    transitions = []
    used_gestures = set()  # indices of gestures already matched

    log_entries = load_transitions_log(session_dir)

    if log_entries:
        print(f"  📖  Loaded {len(log_entries)} transitions from transitions_log.jsonl")
        for entry in log_entries:
            try:
                state_host_time = datetime.fromisoformat(entry["timestamp"]).timestamp()
            except ValueError:
                xml_file = session_dir / entry["xml_file"]
                state_host_time = _parse_xml_timestamp(xml_file, session_date)
                
            xml_file = session_dir / entry["xml_file"]
            fp = entry.get("fingerprint", "")
            
            best_gesture = None
            best_diff = float("inf")
            best_idx = -1
            
            for gi, g in enumerate(gestures):
                if gi in used_gestures:
                    continue
                
                g_host_time = g["uptime"] + offset
                time_diff = state_host_time - g_host_time
                
                if -GESTURE_MATCH_WINDOW_AFTER <= time_diff <= GESTURE_MATCH_WINDOW_BEFORE:
                    if abs(time_diff) < best_diff:
                        best_diff = abs(time_diff)
                        best_gesture = g
                        best_idx = gi
            
            gesture_info = None
            if best_gesture:
                used_gestures.add(best_idx)
                g = best_gesture
                if g["type"] == "tap":
                    gesture_info = f"tap({g['start_x']}, {g['start_y']})"
                else:
                    gesture_info = (
                        f"swipe({g['start_x']}, {g['start_y']} -> "
                        f"{g['end_x']}, {g['end_y']}, dist={g['dist']})"
                    )
                print(f"  🔗  {xml_file.name} ← {g['type']} "
                      f"at ({g['start_x']}, {g['start_y']}) "
                      f"[Δ {best_diff:.2f}s]")

            transitions.append({
                "snapshot_index": entry.get("snap_index", 0),
                "file": xml_file.name,
                "screenshot": entry.get("screenshot"),
                "screen_content": fp,
                "summary": entry.get("summary", ""),
                "elements": extract_interactive_elements(xml_file)[:20] if xml_file.exists() else [],
                "user_interaction": gesture_info
            })
    else:
        # Fallback to manual diffing
        prev_fp = ""
        for i, xml_file in enumerate(xml_files):
            state_host_time = _parse_xml_timestamp(xml_file, session_date)
            
            fp = xml_fingerprint(xml_file)
            if fp == prev_fp:
                continue
                
            # New screen state — find the best matching gesture
            best_gesture = None
            best_diff = float("inf")
            best_idx = -1
            
            for gi, g in enumerate(gestures):
                if gi in used_gestures:
                    continue
                
                g_host_time = g["uptime"] + offset
                # time_diff > 0 means gesture happened AFTER snapshot
                # time_diff < 0 means gesture happened BEFORE snapshot (expected)
                time_diff = state_host_time - g_host_time
                
                # Gesture should have happened BEFORE the snapshot (positive time_diff)
                # with a small window for async lag (negative time_diff up to AFTER limit)
                if -GESTURE_MATCH_WINDOW_AFTER <= time_diff <= GESTURE_MATCH_WINDOW_BEFORE:
                    # Prefer the closest gesture (smallest absolute time_diff)
                    if abs(time_diff) < best_diff:
                        best_diff = abs(time_diff)
                        best_gesture = g
                        best_idx = gi
            
            gesture_info = None
            if best_gesture:
                used_gestures.add(best_idx)
                g = best_gesture
                if g["type"] == "tap":
                    gesture_info = f"tap({g['start_x']}, {g['start_y']})"
                else:
                    gesture_info = (
                        f"swipe({g['start_x']}, {g['start_y']} -> "
                        f"{g['end_x']}, {g['end_y']}, dist={g['dist']})"
                    )
                print(f"  🔗  {xml_file.name} ← {g['type']} "
                      f"at ({g['start_x']}, {g['start_y']}) "
                      f"[Δ {best_diff:.2f}s]")

            transitions.append({
                "snapshot_index": i,
                "file": xml_file.name,
                "screenshot": None,
                "screen_content": fp,
                "summary": xml_fingerprint(xml_file),
                "elements": extract_interactive_elements(xml_file)[:20],
                "user_interaction": gesture_info
            })
            prev_fp = fp

    matched = sum(1 for t in transitions if t["user_interaction"] is not None)
    print(f"  📊  {matched}/{len(transitions)} transitions matched to gestures")
    return transitions

# ── AI Analysis ───────────────────────────────────────────────────────────────

ANALYSIS_PROMPT = """
You are an expert Android UI automation engineer.
I am giving you a series of screen states from an Android app screen recording session.
For each state, you have a text `summary` and a corresponding SCREENSHOT image.
Crucially, some states also include a `user_interaction` which describes the PRECISE action 
the user took on the PREVIOUS screen to trigger this new screen.

Your task:
1. Use both the SCREENSHOTS and the text descriptions to understand what is happening.
2. Identify each distinct SCREEN (e.g., "Home Feed", "Profile", "Reels Tab")
3. Identify the KEY ACTION that led to this screen. 
   - Use the `user_interaction` (tap or swipe) from the current step to figure out what was done on the PREVIOUS screen.
   - Example: If Step 2 says `tap(1300, 2850)` and you see a "Profile" icon at that location in Step 1's screenshot, then Step 2's action was "Tap Profile tab".
4. For each action, identify the BEST automation method:
   - If it's a `tap` that matches a specific text element -> return `xml_tap_text`
   - If it's a `tap` on an icon without text -> return `adb_tap` with the coordinate.
   - If it's a `swipe` -> return `swipe` with start/end coordinates.

Return a JSON array:
[
  {
    "step": 1,
    "screen": "...",
    "action": "...",
    "automation_method": "xml_tap_text | adb_tap | swipe",
    "target": "...",
    "details": "..."
  },
  ...
]

Return ONLY the JSON array.
"""


def analyze_with_gemini(transitions: list[dict], api_key: str, session_dir: Path) -> list[dict]:
    """Call Gemini to interpret the screen transition data with Vision support."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-flash-latest")

    # Simplified text data to stay within token limits alongside images
    transitions_simplified = []
    for t in transitions:
        transitions_simplified.append({
            "step": t["snapshot_index"],
            "summary": t["summary"],
            "user_interaction": t["user_interaction"]
        })

    prompt_parts = [
        ANALYSIS_PROMPT,
        f"\nUI DATA:\n{json.dumps(transitions_simplified, indent=2)}\n"
    ]

    if PIL_AVAILABLE:
        print(f"  🖼️  Loading {len(transitions)} screenshots for Vision analysis...")
        for t in transitions:
            img_name = t.get("screenshot")
            if img_name:
                img_path = session_dir / img_name
                if img_path.exists():
                    try:
                        img = Image.open(img_path)
                        # Ensure RGB for Gemini
                        if img.mode != "RGB":
                            img = img.convert("RGB")
                        prompt_parts.append(f"\n--- STEP {t['snapshot_index']} SCREENSHOT ---")
                        prompt_parts.append(img)
                    except Exception as e:
                        print(f"  ⚠️  Could not load image {img_name}: {e}")

    response = model.generate_content(prompt_parts)
    text = response.text.strip()

    # Strip markdown code blocks if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    return json.loads(text)


# ── Code Generator ────────────────────────────────────────────────────────────

STEP_TEMPLATE = '''
    def step_{num:02d}_{snake_name}(self):
        """
        Step {num}: {action}
        Screen: {screen}
        """
        # Method: {automation_method}
        logger.info("Step {num}: {action}")
        {code}
        time.sleep(WAIT_SHORT)
'''


def method_name(text: str) -> str:
    """Convert a human-readable action to a Python method name."""
    s = re.sub(r"[^a-z0-9 ]", "", text.lower())
    return "_".join(s.split()[:4])


def generate_code(steps: list[dict]) -> str:
    """Generate Python method stubs for each identified step."""
    lines = [
        "# AUTO-GENERATED by analyze_flow.py",
        f"# Generated at: {datetime.now().isoformat()}",
        "# Paste these methods into AppiumPostingService\n",
    ]

    for step in steps:
        num = step.get("step", 0)
        action = step.get("action", "Unknown action")
        screen = step.get("screen", "Unknown screen")
        method = step.get("automation_method", "unknown")
        target = step.get("target_text", "")
        fallback = step.get("fallback", "# TODO: add fallback")
        snake = method_name(action)

        if method == "xml_tap_text" and target:
            code = f'if not self._tap_by_text_xml("{target}", timeout=WAIT_MEDIUM):\n            {fallback}'
        elif method == "adb_tap":
            code = fallback
        elif method == "text_input":
            code = f'# TODO: enter text via clipboard paste\n        # self._enter_caption(text)'
        else:
            code = f"# TODO: implement — {method}\n        pass"

        lines.append(STEP_TEMPLATE.format(
            num=num,
            snake_name=snake,
            action=action,
            screen=screen,
            automation_method=method,
            code=code
        ))

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Analyze a recording session produced by record_flow.py.",
        epilog="Example: python tools/analyze_flow.py recordings/create_reel_20260228_191500"
    )
    parser.add_argument(
        "session_dir",
        help="Path to the recording session directory"
    )
    parser.add_argument(
        "--touches-only",
        action="store_true",
        help="Only parse and display touches, skip AI analysis"
    )
    args = parser.parse_args()

    session_dir = Path(args.session_dir)
    if not session_dir.exists():
        print(f"❌  Session not found: {session_dir}")
        sys.exit(1)

    manifest_path = session_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    print(f"\n🔍  Analyzing session: {session_dir.name}")
    print(f"    Flow: {manifest.get('flow_name', 'unknown')}\n")

    # Parse touches
    touch_log = session_dir / "touches.log"
    taps = parse_touches(touch_log)
    
    if args.touches_only:
        print(f"\n📊  Touch Event Summary:")
        print(f"    Total gestures: {len(taps)}")
        for i, g in enumerate(taps):
            print(f"    {i+1:3d}. [{g['type']:5s}] "
                  f"({g['start_x']:4d}, {g['start_y']:4d}) "
                  f"{'-> (' + str(g['end_x']) + ', ' + str(g['end_y']) + ')' if g['type'] == 'swipe' else ''}"
                  f"  dur={g['duration']:.3f}s  pts={g['points']}")
        return

    # Load XML snapshots
    xml_files = sorted(session_dir.glob("snap_*.xml"))
    print(f"  📋  Loaded {len(xml_files)} XML snapshots")

    if not xml_files:
        print("❌  No XML snapshots found. Did the recorder run correctly?")
        sys.exit(1)

    # Extract session date from directory name (e.g. gesture_test_20260308_221546 -> 20260308)
    session_date = ""
    date_match = re.search(r"(\d{8})_\d{6}$", session_dir.name)
    if date_match:
        session_date = date_match.group(1)
        print(f"  📅  Session date: {session_date[:4]}-{session_date[4:6]}-{session_date[6:8]}")

    offset = 0
    if taps:
        offset = get_uptime_to_host_offset(
            session_dir, taps[0]["uptime"], taps[-1]["uptime"], session_date
        )
        print(f"  👆  {len(taps)} touch events (offset: {offset:.2f}s)")

    # Detect transitions
    print("  🔄  Detecting screen transitions with touch correlation...")
    transitions = detect_screen_transitions(session_dir, xml_files, taps, offset, session_date)
    print(f"  ✅  Found {len(transitions)} distinct screen states\n")

    # Save transition summary (always)
    transitions_path = session_dir / "transitions_analyzed.json"
    with open(transitions_path, "w") as f:
        json.dump(transitions, f, indent=2)
    print(f"  💾  Transitions saved → {transitions_path}")

    # Try AI analysis
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_AI_API_KEY")
    steps = []

    if GEMINI_AVAILABLE and api_key:
        print("\n🤖  Running Gemini AI Vision analysis...")
        try:
            steps = analyze_with_gemini(transitions, api_key, session_dir)
            print(f"  ✅  Identified {len(steps)} automation steps")
        except Exception as e:
            print(f"  ⚠️   AI analysis failed: {e}")
            print("       Falling back to manual transitions review.")
    else:
        print("\n⚠️   Gemini not available (install google-generativeai + set GEMINI_API_KEY).")
        print("     Transitions saved for manual review in transitions.json")

    # Save flow summary
    summary = {
        "session":     session_dir.name,
        "flow_name":   manifest.get("flow_name", "unknown"),
        "analyzed_at": datetime.now().isoformat(),
        "screen_states": len(transitions),
        "touch_events": len(taps),
        "matched_gestures": sum(1 for t in transitions if t["user_interaction"]),
        "steps":       steps,
    }
    summary_path = session_dir / "flow_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  💾  Flow summary saved → {summary_path}")

    # Generate code stubs
    if steps:
        code = generate_code(steps)
        code_path = session_dir / "generated_steps.py"
        code_path.write_text(code)
        print(f"  💾  Generated code  → {code_path}")

    # Final summary
    print(f"\n{'─'*55}")
    print(f"📦  Analysis complete: {session_dir}/")
    if steps:
        print(f"\n📝  Identified steps:")
        for s in steps:
            print(f"    {s.get('step', '?')}. [{s.get('screen','')}] {s.get('action','')}")
    print(f"\n▶️   Next: review {session_dir}/generated_steps.py")
    print(f"    Copy the step methods into AppiumPostingService.\n")


if __name__ == "__main__":
    main()
