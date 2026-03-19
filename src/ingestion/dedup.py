"""
src/ingestion/dedup.py

Content deduplication engine using:
  1. URL-based dedup — canonical URL stored in SQLite (fast, catches re-shares)
  2. pHash-based dedup — perceptual hash of first video keyframe (catches re-uploads)

SQLite DB stored at: data/dedup.db (gitignored)
"""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parents[2] / "data" / "dedup.db"
PHASH_THRESHOLD = 8   # Hamming distance — images within this distance are considered duplicates


def canonical_url(url: str) -> str:
    """Strip tracking params and fragments for stable dedup key."""
    if not url:
        return ""
    p = urlparse(url)
    from urllib.parse import parse_qsl, urlencode
    
    # Essential query params to keep
    KEEP_PARAMS = {'v', 'id', 'shortcode'}
    
    query_params = parse_qsl(p.query)
    clean_query = urlencode([(k, v) for k, v in query_params if k.lower() in KEEP_PARAMS])
    
    # Canonical components: scheme, netloc, path, params (always empty in modern URLs), query, fragment (empty)
    return urlunparse((p.scheme, p.netloc, p.path, '', clean_query, ''))


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


class ContentDedup:
    """
    Thread-safe SQLite-backed dedup engine.

    Tables:
      seen_urls   — URL-level dedup (fast path)
      seen_phash  — Perceptual hash dedup (visual dedup, slower)
      seen_dm_ids — DM message ID tracking (UC1-specific)
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS seen_urls (
                    url_hash    TEXT PRIMARY KEY,
                    url         TEXT,
                    platform    TEXT,
                    source_type TEXT,
                    niche       TEXT,
                    seen_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS seen_phash (
                    phash       TEXT PRIMARY KEY,
                    url_hash    TEXT,
                    seen_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS seen_dm_ids (
                    message_id  TEXT PRIMARY KEY,
                    thread_id   TEXT,
                    url         TEXT,
                    seen_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

    # ── URL dedup ─────────────────────────────────────────────────────────────

    def is_duplicate(self, item) -> bool:  # item: ContentItem
        """Check if this ContentItem has been seen before (URL or shortcode)."""
        key = _sha256(item.dedup_key)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_urls WHERE url_hash = ?", (key,)
            ).fetchone()
            if row:
                logger.debug(f"Dedup URL hit: {item.dedup_key}")
                return True
        return False

    def register(self, item) -> None:  # item: ContentItem
        """Mark a ContentItem as processed."""
        key = _sha256(item.dedup_key)
        with self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO seen_urls
                   (url_hash, url, platform, source_type, niche)
                   VALUES (?, ?, ?, ?, ?)""",
                (key, item.url, item.platform, item.source_type, item.niche)
            )
        logger.debug(f"Dedup registered: {item.dedup_key}")

    # ── DM message ID tracking (UC1) ──────────────────────────────────────────

    def is_dm_seen(self, message_id: str) -> bool:
        """UC1: Check if this DM message ID has already been processed."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_dm_ids WHERE message_id = ?", (message_id,)
            ).fetchone()
        return row is not None

    def register_dm(self, message_id: str, thread_id: str, url: str) -> None:
        """UC1: Mark a DM message as processed."""
        with self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO seen_dm_ids (message_id, thread_id, url)
                   VALUES (?, ?, ?)""",
                (message_id, thread_id, url)
            )
        logger.debug(f"DM seen registered: message={message_id} url={url}")

    # ── pHash dedup (visual) ──────────────────────────────────────────────────

    def compute_phash(self, video_path: Path) -> Optional[str]:
        """
        Extract the first keyframe of a video and compute its perceptual hash.
        Requires ffmpeg on PATH.
        Returns hex string of 64-bit pHash, or None on failure.
        """
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                frame_path = tmp.name

            # Extract first keyframe
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(video_path),
                 "-vframes", "1", "-q:v", "2", frame_path],
                capture_output=True, check=True
            )

            # Compute pHash using pillow_heif or Pillow + custom DCT
            phash = self._pillow_phash(frame_path)
            os.unlink(frame_path)
            return phash
        except Exception as e:
            logger.debug(f"pHash computation failed: {e}")
            return None

    def _pillow_phash(self, image_path: str, hash_size: int = 8) -> str:
        """
        Pure-Pillow DCT-based perceptual hash.
        Returns a 64-bit hex string.
        """
        import struct
        from PIL import Image
        import math

        img = Image.open(image_path).convert("L").resize(
            (hash_size * 4, hash_size * 4), Image.LANCZOS
        )
        pixels = list(img.getdata())
        N = hash_size * 4

        # DCT
        dct = []
        for y in range(N):
            row = []
            for x in range(N):
                val = sum(
                    pixels[yy * N + xx] *
                    math.cos(math.pi * x * (2 * xx + 1) / (2 * N)) *
                    math.cos(math.pi * y * (2 * yy + 1) / (2 * N))
                    for yy in range(N) for xx in range(N)
                )
                row.append(val)
            dct.append(row)

        dct_low = [dct[y][x] for y in range(hash_size) for x in range(hash_size)]
        avg = sum(dct_low[1:]) / (len(dct_low) - 1)
        bits = "".join("1" if v > avg else "0" for v in dct_low)
        return format(int(bits, 2), "016x")

    def _hamming(self, h1: str, h2: str) -> int:
        return bin(int(h1, 16) ^ int(h2, 16)).count("1")

    def is_visual_duplicate(self, video_path: Path) -> bool:
        """Check if video's first frame is visually similar to any seen video."""
        phash = self.compute_phash(video_path)
        if not phash:
            return False
        with self._conn() as conn:
            rows = conn.execute("SELECT phash FROM seen_phash").fetchall()
        for (stored_hash,) in rows:
            if self._hamming(phash, stored_hash) <= PHASH_THRESHOLD:
                logger.info(f"Visual duplicate detected: phash={phash}")
                return True
        return False

    def register_visual(self, video_path: Path, url_hash: str) -> None:
        """Store pHash after download, for future visual dedup checks."""
        phash = self.compute_phash(video_path)
        if not phash:
            return
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seen_phash (phash, url_hash) VALUES (?, ?)",
                (phash, url_hash)
            )
