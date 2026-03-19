import json
import logging
from src.cloud_function.services.vertex_ai_service import VertexAIService

logging.basicConfig(level=logging.INFO)

def test_truncation_recovery():
    service = VertexAIService(project_id="mock-project")
    
    test_cases = [
        # Case 1: Simple object truncation
        ('{"roi": {"ymin": 10', '{"roi": {"ymin": 10}}'),
        # Case 2: List truncation with string
        ('{"words": [{"word": "hello"', '{"words": [{"word": "hello"}]}'),
        # Case 3: Trailing comma truncation
        ('{"items": [1, 2,', '{"items": [1, 2]}'),
        # Case 4: Deeply nested truncation
        ('{"a": {"b": [{"c": "d"', '{"a": {"b": [{"c": "d"}]}}'),
        # Case 5: Empty string
        ('', '{}'),
        # Case 6: Already valid JSON
        ('{"test": true}', '{"test": true}')
    ]
    
    success_count = 0
    for i, (input_str, expected_str) in enumerate(test_cases):
        try:
            recovered = service._close_truncated_json(input_str)
            # Use json.loads to verify validity
            parsed = json.loads(recovered)
            expected_parsed = json.loads(expected_str)
            
            if parsed == expected_parsed:
                logging.info(f"✅ Case {i+1} Passed: '{input_str}' -> '{recovered}'")
                success_count += 1
            else:
                logging.error(f"❌ Case {i+1} Failed: Expected {expected_parsed}, got {parsed}")
        except Exception as e:
            logging.error(f"❌ Case {i+1} Fatal Error: {e}")
            
    print(f"\nSummary: {success_count}/{len(test_cases)} tests passed.")

if __name__ == "__main__":
    test_truncation_recovery()
