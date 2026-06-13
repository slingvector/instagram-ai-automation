"""
src/ingestion/downloaders/ytdlp_downloader.py

yt-dlp based TikTok downloader.
"""
import logging
import subprocess
from pathlib import Path
from typing import Optional
from .base import TikTokDownloaderBase, TikTokDownloadResult
from src.utils.yt_dlp_helper import get_yt_dlp_command

logger = logging.getLogger(__name__)

class YTDLPDownloader(TikTokDownloaderBase):
    def download(self, url: str, filename_hint: str = "") -> TikTokDownloadResult:
        hint = filename_hint or "tiktok"
        safe_hint = "".join(c for c in hint if c.isalnum() or c in "-_")[:60]
        output_template = str(self.output_dir / f"{safe_hint or '%(id)s'}.%(ext)s")

        cmd = get_yt_dlp_command([
            "yt-dlp",
            "--format", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best",
            "--output", output_template,
            "--no-playlist",
            "--write-info-json",
            "--no-warnings",
            "--print", "after_move:filepath",
            url,
        ], proxy=self.proxy)

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if proc.returncode != 0:
                return TikTokDownloadResult(success=False, error=proc.stderr.strip()[:500])

            lines = [l for l in proc.stdout.splitlines() if l.strip()]
            video_path = Path(lines[-1]) if lines else None

            if not video_path or not video_path.exists():
                return TikTokDownloadResult(success=False, error="Output file not found after download")

            return TikTokDownloadResult(success=True, video_path=video_path)

        except Exception as e:
            return TikTokDownloadResult(success=False, error=str(e))
