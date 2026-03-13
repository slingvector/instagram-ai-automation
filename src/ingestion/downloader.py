"""
src/ingestion/downloader.py

Universal content downloader wrapping yt-dlp.
Handles: Instagram, TikTok, YouTube Shorts, Snapchat, Telegram, Facebook Reels, Twitter/X.

Usage:
    dl = UniversalDownloader(output_dir=Path("data/downloads"))
    result = dl.download("https://www.tiktok.com/@user/video/123")
    if result.success:
        process(result.video_path)
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from src.utils.yt_dlp_helper import get_yt_dlp_command

logger = logging.getLogger(__name__)

# yt-dlp format: best video+audio up to 1080p, prefer mp4
_YT_DLP_FORMAT = (
    "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
    "/bestvideo[height<=1080]+bestaudio"
    "/best[height<=1080]/best"
)

_MAX_RETRIES   = 3
_RETRY_DELAY_S = 5


@dataclass
class DownloadResult:
    success:      bool
    video_path:   Optional[Path] = None
    audio_muted:  bool = False           # True if yt-dlp reports copyright mute
    duration_s:   Optional[int]  = None
    title:        Optional[str]  = None
    view_count:   Optional[int]  = None
    like_count:   Optional[int]  = None
    error:        Optional[str]  = None
    raw_info:     dict = field(default_factory=dict)


class UniversalDownloader:
    """
    yt-dlp wrapper with:
    - Retry logic (3 attempts with back-off)
    - Engagement metadata pre-fetch (before committing to download)
    - Optional proxy support
    - Automatic output directory creation
    """

    def __init__(
        self,
        output_dir: Path,
        proxy: Optional[str] = None,
        cookies_file: Optional[Path] = None,  # e.g. instagram_cookies.txt for authed content
    ):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.proxy = proxy
        self.cookies_file = cookies_file

    # ── Public API ────────────────────────────────────────────────────────────

    def prefetch_metadata(self, url: str) -> dict:
        """
        Fetch engagement metadata WITHOUT downloading the video.
        Use this to filter low-quality content before committing bandwidth.
        Returns dict with: view_count, like_count, duration, title, id
        """
        cmd = self._base_cmd() + [
            "--skip-download",
            "--print", "%(id)s|%(title)s|%(duration)s|%(view_count)s|%(like_count)s",
            url,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                parts = result.stdout.strip().split("|")
                if len(parts) >= 5:
                    return {
                        "id":         parts[0],
                        "title":      parts[1],
                        "duration":   int(parts[2]) if parts[2].isdigit() else None,
                        "view_count": int(parts[3]) if parts[3].isdigit() else 0,
                        "like_count": int(parts[4]) if parts[4].isdigit() else 0,
                    }
        except Exception as e:
            logger.debug(f"Metadata prefetch failed for {url}: {e}")
        return {}

    def download(self, url: str, filename_hint: str = "") -> DownloadResult:
        """
        Download a video from any supported platform.
        Retries up to _MAX_RETRIES times on failure.
        """
        for attempt in range(1, _MAX_RETRIES + 1):
            result = self._attempt_download(url, filename_hint)
            if result.success:
                return result
            logger.warning(f"Download attempt {attempt}/{_MAX_RETRIES} failed: {result.error}")
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_S * attempt)

        return DownloadResult(success=False, error=f"All {_MAX_RETRIES} attempts failed for {url}")

    def meets_engagement_threshold(self, metadata: dict, min_views: int = 100_000, min_likes: int = 0) -> bool:
        """Quick check if content is worth downloading based on prefetched metadata."""
        return (
            metadata.get("view_count", 0) >= min_views and
            metadata.get("like_count", 0) >= min_likes
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _attempt_download(self, url: str, filename_hint: str) -> DownloadResult:
        safe_hint = "".join(c for c in filename_hint if c.isalnum() or c in "-_")[:60]
        output_template = str(self.output_dir / f"{safe_hint or '%(id)s'}.%(ext)s")

        cmd = self._base_cmd() + [
            "--format",          _YT_DLP_FORMAT,
            "--output",          output_template,
            "--no-playlist",
            "--write-info-json",
            "--no-warnings",
            "--print", "after_move:filepath",   # Print final file path after merge
            url,
        ]

        logger.info(f"Downloading: {url}")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()

            if proc.returncode != 0:
                return DownloadResult(success=False, error=stderr[:500])

            # Last line of stdout is the final file path (from --print after_move:filepath)
            lines = [l for l in stdout.splitlines() if l.strip()]
            video_path = Path(lines[-1]) if lines else None

            if not video_path or not video_path.exists():
                # Fallback: glob for the most recently created file in output_dir
                candidates = sorted(
                    self.output_dir.glob("*.mp4"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                )
                video_path = candidates[0] if candidates else None

            if not video_path or not video_path.exists():
                return DownloadResult(success=False, error="Output file not found after download")

            audio_muted = "audio track" in stderr.lower() and "muted" in stderr.lower()

            return DownloadResult(
                success=True,
                video_path=video_path,
                audio_muted=audio_muted,
            )

        except subprocess.TimeoutExpired:
            return DownloadResult(success=False, error="Download timed out after 300s")
        except Exception as e:
            return DownloadResult(success=False, error=str(e))

    def _base_cmd(self) -> list[str]:
        # We start with a minimal cmd and let the helper wrap it with 
        # formats, proxies, and cookies.
        return get_yt_dlp_command(["yt-dlp"], proxy=self.proxy)
