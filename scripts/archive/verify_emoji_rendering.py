import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.media_factory.utils.ass_generator import ASSGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_emoji_rendering():
    print("\n--- Testing 'Dopamine-Heavy' Emoji Rendering ---")
    gen = ASSGenerator()
    
    # Mock transcription data with sentiment clusters
    mock_transcription = {
        "words": [
            {"word": "This", "start": 0.0, "end": 0.2},
            {"word": "is", "start": 0.2, "end": 0.4},
            {"word": "insane", "start": 0.4, "end": 0.6},
            {"word": "viral", "start": 0.6, "end": 0.8},
            {"word": "growth", "start": 0.8, "end": 1.0}
        ],
        "sentiment_clusters": [
            {
                "start": 0.0, 
                "end": 1.2, 
                "text_emojis": "🔥🚀", 
                "floating_emojis": "💸💰", 
                "intensity": 0.9
            }
        ],
        "duration": 5.0
    }
    
    output_path = "/tmp/test_emoji.ass"
    gen.generate(mock_transcription, output_path, headline="CRAZY GROWTH")
    
    if os.path.exists(output_path):
        with open(output_path, "r") as f:
            content = f.read()
            
        print(f"Generated {output_path}")
        
        # Checks
        has_emoji_style = "Style: Emoji" in content
        has_font_switch = "{\\fnApple Color Emoji}" in content
        has_floating_layer = "Dialogue: 1," in content
        has_move = "\\move(" in content
        
        print(f"Emoji Style: {'✅' if has_emoji_style else '❌'}")
        print(f"Font Switching: {'✅' if has_font_switch else '❌'}")
        print(f"Floating Layer (Layer 1): {'✅' if has_floating_layer else '❌'}")
        print(f"Drift Animation (\move): {'✅' if has_move else '❌'}")
        
        if all([has_emoji_style, has_font_switch, has_floating_layer, has_move]):
            print("\n🎉 EMOJI VERIFICATION PASSED!")
            return True
    
    print("\n🚨 EMOJI VERIFICATION FAILED!")
    return False

if __name__ == "__main__":
    if test_emoji_rendering():
        sys.exit(0)
    else:
        sys.exit(1)
