import logging
import os
import json
from src.utils.gcp_logging import setup_cloud_logging

def test_unified_observability():
    print("🏁 Starting Unified Observability Verification...")
    
    # Initialize the new logger
    setup_cloud_logging()
    logger = logging.getLogger("test_observability")
    
    # Generate some test logs with metadata
    print("📝 Generating test logs...")
    logger.info("Industrial run starting...", extra={"metadata": {"batch_id": "test_100", "total": 100}})
    logger.warning("Simulated device lag detected.", extra={"metadata": {"latency_ms": 500}})
    logger.error("Simulated posting fail.", extra={"metadata": {"job_id": "job_123", "retry": True}})
    
    # Verify local file presence
    log_file = os.path.abspath("logs/unified_industrial.log")
    telemetry_file = os.path.abspath("logs/telemetry.jsonl")
    
    if os.path.exists(log_file):
        print(f"✅ Local Log File Found: {log_file}")
    else:
        print("❌ Local Log File MISSING!")

    if os.path.exists(telemetry_file):
        print(f"✅ Telemetry JSONL Found: {telemetry_file}")
        # Verify JSON validity
        with open(telemetry_file, "r") as f:
            last_line = f.readlines()[-1]
            try:
                data = json.loads(last_line)
                print(f"✅ Telemetry JSON valid. Message: {data['message']}")
                if "metadata" in data:
                    print(f"✅ Metadata correctly captured: {data['metadata']}")
            except Exception as e:
                print(f"❌ Telemetry JSON invalid: {e}")
    else:
        print("❌ Telemetry JSONL MISSING!")

if __name__ == "__main__":
    test_unified_observability()
