import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_pipeline(db_path="data/bulk_post_state.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Identify items that are stuck or failed
    # We'll reset FAILED items to SCANNED so they can be re-evaluated
    # and we'll clear PROCESSING if it's been there too long (orphaned)
    
    cursor.execute("UPDATE reel_states SET state='SCANNED' WHERE state='FAILED'")
    logger.info(f"Reset {cursor.rowcount} FAILED reels to SCANNED.")
    
    cursor.execute("UPDATE reel_states SET state='SCANNED' WHERE state='PROCESSING'")
    logger.info(f"Reset {cursor.rowcount} PROCESSING reels to SCANNED.")
    
    cursor.execute("UPDATE reel_states SET state='SCANNED' WHERE state='POSTING'")
    logger.info(f"Reset {cursor.rowcount} POSTING reels to SCANNED.")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    reset_pipeline()
