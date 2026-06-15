#!/usr/bin/env python3
"""
rotate_page_state.py: Archives the current reel_states.db and initializes a fresh one.
Used when pivoting to a new Instagram page to prevent data contamination.
"""
import os
import shutil
import sqlite3
from datetime import datetime

DB_PATH = "data/reel_states.db"
ARCHIVE_DIR = "data/archive"

def rotate():
    if not os.path.exists(DB_PATH):
        print(f"⚠️ No database found at {DB_PATH}. Nothing to rotate.")
        return

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    
    # Generate archive filename with timestamp
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = os.path.join(ARCHIVE_DIR, f"reel_states_legacy_{ts}.db")
    
    print(f"📦 Archiving current database to {archive_path}...")
    shutil.copy2(DB_PATH, archive_path)
    
    print(f"🧹 Clearing active database: {DB_PATH}")
    # We delete and let the StateManager re-create it to ensure schema is fresh
    os.remove(DB_PATH)
    
    print("✅ Rotation complete. A fresh database will be created on the next run.")

if __name__ == "__main__":
    rotate()
