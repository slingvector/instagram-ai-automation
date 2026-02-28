#!/usr/bin/env python3
"""
analyze_flow.py — AI Flow Analyzer
====================================
Reads a recording session produced by record_flow.py and uses Gemini Vision
to understand what happened on screen at each step. Outputs:

  - flow_summary.json   : structured step-by-step description
  - generated_steps.py  : Python code stub for appium_posting_service.py

Usage:
    python tools/analyze_flow.py recordings/<session_folder>

Example:
    python tools/analyze_flow.py recordings/create_reel_20260228_191500

Requirements:
    pip install google-generativeai pillow
    GOOGLE_APPLICATION_CREDENTIALS must point to your GCP service account key
    OR set GEMINI_API_KEY in .env
"""

import sys
import os
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

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


def detect_screen_transitions(xml_files: list[Path]) -> list[dict]:
    """
    Compare consecutive XML snapshots.
    When the on-screen text changes significantly, mark it as a transition.
    Returns a list of key transition moments.
    """
    transitions = []
    prev_fp = ""

    for i, xml_file in enumerate(xml_files):
        fp = xml_fingerprint(xml_file)
        if fp != prev_fp:
            transitions.append({
                "snapshot_index": i,
                "file": xml_file.name,
                "screen_content": fp,
                "elements": extract_interactive_elements(xml_file)[:20]
            })
            prev_fp = fp

    return transitions


# ── AI Analysis ───────────────────────────────────────────────────────────────

ANALYSIS_PROMPT = """
You are an expert Android UI automation engineer.
I am giving you a series of screen states from an Instagram screen recording session.
Each state contains the visible UI elements at that moment.

Your task:
1. Identify each distinct SCREEN the user visited (e.g., "Home Feed", "New Reel Gallery", "Reel Editor", "Caption Screen")
2. Identify the KEY ACTION the user took at each screen transition
3. For each action, identify the BEST way to automate it:
   - If there's text visible → use text-based XML tap
   - If it's an image/icon → note the resource-id or position
   - If it's a form input → note it's a text entry

Return a JSON array like this:
[
  {
    "step": 1,
    "screen": "Instagram Home Feed",
    "action": "Tapped the + (Create) button",
    "automation_method": "xml_tap_text",
    "target_text": "New post",
    "fallback": "adb_tap(96, 225)"
  },
  ...
]

Here are the screen transitions observed during this recording:

{transitions}

Return ONLY the JSON array.
"""


def analyze_with_gemini(transitions: list[dict], api_key: str) -> list[dict]:
    """Call Gemini to interpret the screen transition data."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    transitions_text = json.dumps(transitions, indent=2)
    prompt = ANALYSIS_PROMPT.format(transitions=transitions_text)

    response = model.generate_content(prompt)
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
    import re
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
    if len(sys.argv) < 2:
        print("Usage: python tools/analyze_flow.py recordings/<session_folder>")
        sys.exit(1)

    session_dir = Path(sys.argv[1])
    if not session_dir.exists():
        print(f"❌  Session not found: {session_dir}")
        sys.exit(1)

    manifest_path = session_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    print(f"\n🔍  Analyzing session: {session_dir.name}")
    print(f"    Flow: {manifest.get('flow_name', 'unknown')}\n")

    # Load XML snapshots
    xml_files = sorted(session_dir.glob("snap_*.xml"))
    print(f"  📋  Loaded {len(xml_files)} XML snapshots")

    if not xml_files:
        print("❌  No XML snapshots found. Did the recorder run correctly?")
        sys.exit(1)

    # Detect transitions
    print("  🔄  Detecting screen transitions...")
    transitions = detect_screen_transitions(xml_files)
    print(f"  ✅  Found {len(transitions)} distinct screen states\n")

    # Save transition summary (always)
    transitions_path = session_dir / "transitions.json"
    with open(transitions_path, "w") as f:
        json.dump(transitions, f, indent=2)
    print(f"  💾  Transitions saved → {transitions_path}")

    # Try AI analysis
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_AI_API_KEY")
    steps = []

    if GEMINI_AVAILABLE and api_key:
        print("\n🤖  Running Gemini AI analysis...")
        try:
            steps = analyze_with_gemini(transitions, api_key)
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
