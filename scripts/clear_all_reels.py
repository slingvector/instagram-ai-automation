# scripts/clear_all_reels.py
import sqlite3
import os

def main():
    print("🧹 Starting clean database wipe...")
    
    # 1. Clear State Manager
    state_db = "data/bulk_post_state.db"
    if os.path.exists(state_db):
        try:
            conn = sqlite3.connect(state_db)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reel_states")
            conn.commit()
            print(f"✅ Cleared all rows in {state_db} (reel_states table)")
        except Exception as e:
            print(f"❌ Error clearing {state_db}: {e}")
        finally:
            conn.close()
    else:
        print(f"ℹ️ {state_db} does not exist.")
        
    # 2. Clear Deduplication cache
    dedup_db = "data/dedup.db"
    if os.path.exists(dedup_db):
        try:
            conn = sqlite3.connect(dedup_db)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM seen_urls")
            cursor.execute("DELETE FROM seen_phash")
            cursor.execute("DELETE FROM seen_dm_ids")
            conn.commit()
            print(f"✅ Cleared all rows in {dedup_db} (seen_urls, seen_phash, seen_dm_ids)")
        except Exception as e:
            print(f"❌ Error clearing {dedup_db}: {e}")
        finally:
            conn.close()
    else:
        print(f"ℹ️ {dedup_db} does not exist.")

    print("✨ Database reset complete!")

if __name__ == "__main__":
    main()
