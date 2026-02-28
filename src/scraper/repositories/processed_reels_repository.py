import sqlite3
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class ProcessedReelsRepository:
    """
    Repository layer for managing processed Reel URLs.
    Handles all SQLite database interactions.
    """
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initializes the local SQLite database for URL deduplication."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS scraped_reels (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT UNIQUE NOT NULL,
                        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
            raise

    def is_url_processed(self, url: str) -> bool:
        """Checks if a URL has already been processed by querying the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT 1 FROM scraped_reels WHERE url = ?', (url,))
                result = cursor.fetchone()
                return result is not None
        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return False

    def mark_url_processed(self, url: str) -> bool:
        """Inserts a successfully processed URL into the database ledger."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO scraped_reels (url) VALUES (?)', (url,))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            logger.warning(f"URL {url} already exists in the database.")
            return False
        except sqlite3.Error as e:
            logger.error(f"Database insert error: {e}")
            return False
