import json
from src.cloud_function.services.vertex_ai_service import VideoTranscription, SentimentCluster, WordTimestamp

def test_pydantic_validation():
    print("🏁 Test 4: Validating Pydantic Schemas...")
    
    # Mock a perfectly structured Gemini response
    mock_data = {
        "words": [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "World", "start": 0.5, "end": 1.0}
        ],
        "sentiment_clusters": [
            {
                "start": 0.0,
                "end": 1.0,
                "sentiment": "happy",
                "text_emojis": "😊",
                "reaction_pool": "vibe_success vibe_energy",
                "burst_count": 3,
                "intensity": 0.8
            }
        ]
    }
    
    try:
        # Validate data against the schema
        transcription = VideoTranscription(**mock_data)
        print("✅ Pydantic Validation Passed!")
        print(f"📦 Transcription has {len(transcription.words)} words.")
        print(f"📦 First Sentiment Cluster: {transcription.sentiment_clusters[0].sentiment}")
    except Exception as e:
        print(f"❌ Pydantic Validation Failed: {e}")

if __name__ == "__main__":
    test_pydantic_validation()
