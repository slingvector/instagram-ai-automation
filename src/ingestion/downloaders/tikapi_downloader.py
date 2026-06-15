"""
src/ingestion/downloaders/tikapi_downloader.py

TikAPI based TikTok downloader for premium, high-reliability ingestion.
"""
import logging
import requests
import os
from pathlib import Path
from typing import Optional
from .base import TikTokDownloaderBase, TikTokDownloadResult

logger = logging.getLogger(__name__)

class TikAPIDownloader(TikTokDownloaderBase):
    def download(self, url: str, filename_hint: str = "") -> TikTokDownloadResult:
        api_key = os.getenv("TIKAPI_KEY")
        if not api_key:
            return TikTokDownloadResult(success=False, error="TIKAPI_KEY environment variable not set")
            
        logger.info(f"Attempting premium download via TikAPI: {url}")
        
        # This is a representative implementation of TikAPI flow
        try:
            # 1. Fetch video metadata and download URL
            response = requests.get(
                "https://api.tikapi.io/public/video",
                params={"url": url},
                headers={"X-API-KEY": api_key},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            # 2. Extract no-watermark video URL
            video_url = data.get("video", {}).get("no_watermark_url")
            if not video_url:
                return TikTokDownloadResult(success=False, error="No watermark-free URL found in TikAPI response")
                
            # 3. Download the actual file
            hint = filename_hint or "tikapi"
            safe_hint = "".join(c for c in hint if c.isalnum() or c in "-_")[:60]
            video_path = self.output_dir / f"{safe_hint}.mp4"
            
            with requests.get(video_url, stream=True) as r:
                r.raise_for_status()
                with open(video_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        
            if video_path.exists():
                logger.info(f"✅ TikAPI Download Success: {video_path}")
                return TikTokDownloadResult(success=True, video_path=video_path)
            else:
                return TikTokDownloadResult(success=False, error="File saved but not found on disk")
                
        except Exception as e:
            logger.error(f"TikAPI download failed: {e}")
            return TikTokDownloadResult(success=False, error=str(e))
