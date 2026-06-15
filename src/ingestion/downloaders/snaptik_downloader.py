"""
src/ingestion/downloaders/snaptik_downloader.py

Playwright-based TikTok downloader for watermark-free content via SnapTik.
"""
import logging
import time
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright
from .base import TikTokDownloaderBase, TikTokDownloadResult

logger = logging.getLogger(__name__)

class SnapTikDownloader(TikTokDownloaderBase):
    def download(self, url: str, filename_hint: str = "") -> TikTokDownloadResult:
        logger.info(f"Attempting watermark-free download via SnapTik: {url}")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            
            try:
                # 1. Navigate to SnapTik
                page.goto("https://snaptik.app/", wait_until="networkidle")
                
                # 2. Input TikTok URL
                page.fill("input#url", url)
                page.click("button.button-go")
                
                # 3. Wait for download links to appear
                # SnapTik shows several download servers
                page.wait_for_selector("a.download-block", timeout=30000)
                
                # 4. Handle the download
                with page.expect_download() as download_info:
                    # Click the first download button available
                    page.click("a.download-block")
                
                download = download_info.value
                
                # Use filename hint if provided
                hint = filename_hint or "snaptik"
                safe_hint = "".join(c for c in hint if c.isalnum() or c in "-_")[:60]
                video_path = self.output_dir / f"{safe_hint}_{int(time.time())}.mp4"
                
                download.save_as(video_path)
                browser.close()
                
                if video_path.exists():
                    logger.info(f"✅ SnapTik Download Success: {video_path}")
                    return TikTokDownloadResult(success=True, video_path=video_path)
                else:
                    return TikTokDownloadResult(success=False, error="File saved but not found on disk")
                    
            except Exception as e:
                logger.error(f"SnapTik download failed: {e}")
                browser.close()
                return TikTokDownloadResult(success=False, error=str(e))
