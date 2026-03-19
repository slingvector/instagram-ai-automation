import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.media_factory.utils.ass_generator import ASSGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_emoji_burst():
    print("\n--- Testing 'Burst Mode' (Story-Pop) Emoji Storm [v3 - Noto Fix] ---")
    gen = ASSGenerator()
    
    # Mock transcription with a high-density burst
    mock_transcription = {
        "words": [
            {"word": "CRAZY", "start": 0.0, "end": 0.3},
            {"word": "GAINS", "start": 0.3, "end": 0.6},
            {"word": "EVERYONE", "start": 0.6, "end": 1.0}
        ],
        "sentiment_clusters": [
            {
                "start": 0.0, 
                "end": 1.2, 
                "text_emojis": "🔥🚀", 
                "reaction_pool": "🔥🚀💸💰💎✨🍒🌈", 
                "burst_count": 8, 
                "intensity": 1.0
            }
        ],
        "duration": 5.0
    }
    
    output_path = "/tmp/test_burst_v3.ass"
    gen.generate(mock_transcription, output_path, headline="BURST TEST")
    
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        print(f"Generated {output_path}\n")
        
        # Base Kinetic Checks
        reaction_lines = [l for l in lines if l.startswith("Dialogue: 1,")]
        fade_out_count = sum(1 for l in lines if "\\alpha&HFF&" in l)
        move_count = sum(1 for l in lines if "\\move(" in l)
        jitter_check = len(set([l.split(",")[1] for l in reaction_lines])) > 1
        
        # REAL-WORLD PARITY CHECKS (v3)
        # 1. Verify the header explicitly maps the Emoji style to the open-source font
        style_defined_v3 = any("Style: Emoji,Noto Color Emoji," in l for l in lines)
        
        # 2. Ensure Burst lines (Layer 1) DO NOT have inline \fn overrides that break the header style
        # We check the text payload at the end of the line (after the 9th comma)
        no_inline_override = all("\\fn" not in l.split(",,")[-1] for l in reaction_lines)
        
        # 3. Tofu Blacklist: Ensure Apple's proprietary bitmap font is completely purged
        tofu_leak_resolved = not any("Apple Color Emoji" in l for l in lines)
        
        print(f"Burst Density (Count): {len(reaction_lines)} (Expected 8)")
        print(f"Fade-Out Animations: {'✅' if fade_out_count >= 8 else '❌'}")
        print(f"Trajectory Moves:    {'✅' if move_count >= 8 else '❌'}")
        print(f"Jittered Timing:     {'✅' if jitter_check else '❌'}")
        print("-" * 40)
        print(f"Header Maps to Noto Color Emoji: {'✅' if style_defined_v3 else '❌'}")
        print(f"Clean Layer 1 (No \\fn Hijacking): {'✅' if no_inline_override else '❌'}")
        print(f"Tofu Blacklist (No Apple Bitmap): {'✅' if tofu_leak_resolved else '🚨 FAILED'}")
        
        # Validation Logic
        success = (
            len(reaction_lines) == 8 and 
            fade_out_count >= 8 and 
            move_count >= 8 and 
            jitter_check and
            style_defined_v3 and
            no_inline_override and
            tofu_leak_resolved
        )
        
        if success:
            print("\n🎉 REAL-WORLD VERIFICATION PASSED! Ready for FFmpeg rendering.")
            return True
    
    print("\n🚨 BURST MODE VERIFICATION FAILED!")
    return False

if __name__ == "__main__":
    if test_emoji_burst():
        sys.exit(0)
    else:
        sys.exit(1)
