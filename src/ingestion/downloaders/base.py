"""
src/ingestion/downloaders/base.py

Base interface for all TikTok downloader plugins.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class TikTokDownloadResult:
    success: bool
    video_path: Optional[Path] = None
    error: Optional[str] = None
    metadata: dict = None

class TikTokDownloaderBase(ABC):
    """
    Abstract base class for TikTok download strategies.
    """
    def __init__(self, output_dir: Path, proxy: Optional[str] = None):
        self.output_dir = output_dir
        self.proxy = proxy
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def download(self, url: str, filename_hint: str = "") -> TikTokDownloadResult:
        """
        Download a TikTok video from the given URL.
        """
        pass
