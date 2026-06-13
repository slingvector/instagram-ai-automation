import os
import sqlite3
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from src.ingestion.dedup import canonical_url

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "bulk_post_state.db")

class ReelState:
    SCANNED = "SCANNED"
    DISCOVERED = "DISCOVERED"
    DOWNLOADED = "DOWNLOADED"
    CAPTIONED = "CAPTIONED"
    JOB_CREATED = "JOB_CREATED"
    MEDIA_PROCESSED = "MEDIA_PROCESSED"
    SYNCED_TO_DRIVE = "SYNCED_TO_DRIVE"
    POSTING = "POSTING"
    POSTED = "POSTED"
    FAILED = "FAILED"

class StateManager:
    """
    SQLite-backed state manager for tracking the progress of reels
    through the bulk posting pipeline.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reel_states (
                    url TEXT PRIMARY KEY,
                    title TEXT,
                    platform TEXT,
                    source TEXT,
                    niche TEXT,
                    state TEXT,
                    gcs_uri TEXT,
                    ai_metadata TEXT,
                    job_id TEXT,
                    processed_uri TEXT,
                    drive_folder_id TEXT,
                    tx_hash TEXT,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Migration checks
            try:
                cursor.execute("ALTER TABLE reel_states ADD COLUMN niche TEXT")
            except sqlite3.OperationalError: pass
            try:
                cursor.execute("ALTER TABLE reel_states ADD COLUMN platform TEXT")
            except sqlite3.OperationalError: pass
            try:
                cursor.execute("ALTER TABLE reel_states ADD COLUMN drive_folder_id TEXT")
            except sqlite3.OperationalError: pass
            conn.commit()

    def add_discovered_reel(self, url: str, title: str, platform: str, source: str, niche: str = "general") -> bool:
        """Adds a new reel if it doesn't already exist. Returns True if added."""
        clean_url = canonical_url(url)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO reel_states (url, title, platform, source, niche, state)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (clean_url, title, platform, source, niche, ReelState.SCANNED))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                # Already exists
                return False

    def get_reel(self, url: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reel_states WHERE url = ?", (url,))
            row = cursor.fetchone()
            if row:
                data = dict(row)
                if data.get("ai_metadata"):
                    data["ai_metadata"] = json.loads(data["ai_metadata"])
                return data
            return None

    def get_pending_reels(self, include_failed: bool = False) -> List[Dict[str, Any]]:
        """Returns reels that are not POSTED. Optionally include FAILED for retries."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            states = [ReelState.POSTED, ReelState.POSTING]
            if not include_failed:
                states.append(ReelState.FAILED)
                
            placeholders = ', '.join(['?'] * len(states))
            query = f"SELECT * FROM reel_states WHERE state NOT IN ({placeholders}) ORDER BY created_at ASC"
            
            cursor.execute(query, tuple(states))
            
            reels = []
            for row in cursor.fetchall():
                data = dict(row)
                if data.get("ai_metadata"):
                    data["ai_metadata"] = json.loads(data["ai_metadata"])
                reels.append(data)
            return reels

    def update_state(self, url: str, state: str, **kwargs):
        """Updates the state and optionally other fields like gcs_uri, job_id, etc."""
        update_fields = ["state = ?", "updated_at = CURRENT_TIMESTAMP"]
        values = [state]

        # Valid fields to update mapping
        # Ensure we only update columns that exist
        valid_columns = ["gcs_uri", "ai_metadata", "job_id", "processed_uri", "drive_folder_id", "tx_hash", "error_message", "title"]
        
        for key, val in kwargs.items():
            if key in valid_columns:
                update_fields.append(f"{key} = ?")
                if key == "ai_metadata" and isinstance(val, dict):
                    values.append(json.dumps(val))
                else:
                    values.append(val)

        values.append(url)
        query = f"UPDATE reel_states SET {', '.join(update_fields)} WHERE url = ?"
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(values))
            conn.commit()

    def mark_failed(self, url: str, error: str):
        logger.error(f"Reel {url} FAILED: {error}")
        self.update_state(url, ReelState.FAILED, error_message=str(error))

