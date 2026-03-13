import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.media_factory.utils.ass_generator import ASSGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_emoji_burst():
    print("\n--- Testing 'Burst Mode' (Story-Pop) Emoji Storm ---")
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
    
    output_path = "/tmp/test_burst.ass"
    gen.generate(mock_transcription, output_path, headline="BURST TEST")
    
    if os.path.exists(output_path):
        with open(output_path, "r") as f:
            lines = f.readlines()
            
        print(f"Generated {output_path}")
        
        # Checks
        reaction_lines = [l for l in lines if l.startswith("Dialogue: 1,")]
        fade_out_count = sum(1 for l in lines if "\\alpha&HFF&" in l)
        move_count = sum(1 for l in lines if "\\move(" in l)
        jitter_check = len(set([l.split(",")[1] for l in reaction_lines])) > 1
        
        # PRO PARITY CHECKS (v2.6)
        # 1. Ensure Emoji style is defined
        style_defined = any("Style: Emoji," in l and "Apple Color Emoji" in l for l in lines)
        
        # 2. Ensure ALL burst lines use the \fnEmoji style alias (not hardcoded font name)
        # Using the style alias ensures FFmpeg's renderer handles the fallback correctly
        style_alias_v2 = all("\\fnEmoji" in l for l in reaction_lines)
        
        # 3. Blacklist direct font name usage in kinetic tags (this caused the 'tofu' bug)
        tofu_leak = any("\\fnApple Color Emoji" in l for l in lines)
        
        print(f"Burst Density (Count): {len(reaction_lines)} (Expected 8)")
        print(f"Fade-Out Animations: {'✅' if fade_out_count >= 8 else '❌'}")
        print(f"Trajectory Moves: {'✅' if move_count >= 8 else '❌'}")
        print(f"Jittered Timing: {'✅' if jitter_check else '❌'}")
        print(f"Emoji Style Defined: {'✅' if style_defined else '❌'}")
        print(f"Font Mapping (\fnEmoji): {'✅' if style_alias_v2 else '❌'}")
        print(f"Tofu Font Leak Detection: {'✅' if not tofu_leak else '🚨 FAILED (tofu leak detected)'}")
        
        # Validation Logic
        success = (
            len(reaction_lines) == 8 and 
            fade_out_count >= 8 and 
            move_count >= 8 and 
            jitter_check and
            style_defined and
            style_alias_v2 and
            not tofu_leak
        )
        
        if success:
            print("\n🎉 BURST MODE VERIFICATION PASSED (HARDENED)!")
            return True
    
    print("\n🚨 BURST MODE VERIFICATION FAILED!")
    return False

if __name__ == "__main__":
    if test_emoji_burst():
        sys.exit(0)
    else:
        sys.exit(1)
