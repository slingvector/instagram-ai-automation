import sys
import os
import logging
from typing import Set

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.media_factory.styles.template_manager import TemplateManager
from src.media_factory.utils.ass_generator import ASSGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_template_execution_parity(niche: str):
    print(f"\n--- Testing Execution Parity for Niche: '{niche}' ---")
    tm = TemplateManager()
    gen = ASSGenerator()
    
    tid = tm.select_template_by_niche(niche)
    template = tm.templates.get(tid)
    
    print(f"Selected Template: {tid}")
    
    # Mock data
    mock_transcription = {
        "words": [{"word": "TEST", "start": 0.0, "end": 1.0}],
        "duration": 5.0
    }
    output_path = f"/tmp/test_parity_{tid}.ass"
    
    gen.generate(mock_transcription, output_path, template=template)
    
    if os.path.exists(output_path):
        with open(output_path, "r") as f:
            content = f.read()
            
        # Parity Checks
        expected_font = template.get("font", "Arial")
        expected_size = template.get("font_size", 70)
        
        # Verify font propagation in Default style
        font_match = f"Style: Default,{expected_font},{expected_size}" in content
        
        # Verify MarginV propagation from layout
        layout = template.get("layout", "center_third")
        expected_margin = 720
        if layout == "center_lower": expected_margin = 320
        if layout == "minimal_lower": expected_margin = 250
        
        margin_match = f",,,,{expected_margin}," in content or f",,,{expected_margin}," in content
        # Note: ASS format can be tricky with commas, let's check the specific Dialogue line if possible
        # Dialogue: 0,0:00:00.00,0:00:01.30,Default,,100,100,720,,...
        dialog_line = [l for l in content.splitlines() if l.startswith("Dialogue: 0,")][0]
        margin_verified = f",100,100,{expected_margin}," in dialog_line

        print(f"Template Font ({expected_font}): {'✅' if font_match else '❌'}")
        print(f"Template Font Size ({expected_size}): {'✅' if font_match else '❌'}")
        print(f"Layout Margin ({expected_margin}): {'✅' if margin_verified else '❌'}")
        
        if font_match and margin_verified:
            print(f"🎉 EXECUTION PARITY PASSED FOR {tid}!")
            return True
        
    print(f"🚨 EXECUTION PARITY FAILED FOR {tid}!")
    return False

def test_niche_variety(niche: str, iterations: int = 10):
    print(f"\n--- Testing Variety for Niche: '{niche}' ---")
    tm = TemplateManager()
    selected_templates = []
    for i in range(iterations):
        tid = tm.select_template_by_niche(niche)
        selected_templates.append(tid)
        
    unique_count = len(set(selected_templates))
    print(f"Iterations: {iterations}")
    print(f"Unique Templates Selected: {unique_count}")
    print(f"Sequence: {selected_templates}")
    
    if unique_count > 1:
        print(f"✅ PASSED: Found variety for '{niche}'")
    else:
         print(f"❌ FAILED: No variety for '{niche}'")
    
    return unique_count

if __name__ == "__main__":
    niches = ["news", "sports", "tech", "business", "nature"]
    all_passed = True
    
    for n in niches:
        # Check variety
        if test_niche_variety(n) <= 1:
            all_passed = False
        
        # Check execution parity
        if not test_template_execution_parity(n):
            all_passed = False
            
    if all_passed:
        print("\n🎉 ALL DYNAMIC & PARITY TESTS PASSED!")
        sys.exit(0)
    else:
        print("\n🚨 SOME TESTS FAILED. CHECK LOGS ABOVE.")
        sys.exit(1)
