import os
import sys
import logging
import shutil
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

def get_yt_dlp_command(base_args: List[str], proxy: Optional[str] = None) -> List[str]:
    """
    Wraps yt-dlp arguments with cookie flags and handles cross-platform path resolution.
    It automatically looks for yt-dlp in the current venv or system paths.
    """
    cmd = base_args.copy()
    
    # 1. Resolve yt-dlp path
    # If we are in a venv, yt-dlp is usually in the same directory as the python executable
    venv_bin = Path(sys.executable).parent
    yt_dlp_path = venv_bin / "yt-dlp"
    
    if yt_dlp_path.exists():
        cmd[0] = str(yt_dlp_path)
    else:
        # Fallback to system search
        found = shutil.which("yt-dlp")
        if found:
            cmd[0] = found
        else:
            logger.warning("yt-dlp executable not found in venv or system PATH.")

    # 2. Add Cookies
    cookies_path = os.getenv("YT_DLP_COOKIES_PATH")
    cookies_browser = os.getenv("YT_DLP_COOKIES_FROM_BROWSER")

    if cookies_path and os.path.exists(cookies_path):
        logger.info(f"Using yt-dlp cookies from file: {cookies_path}")
        cmd.insert(1, "--cookies")
        cmd.insert(2, cookies_path)
    elif cookies_browser:
        logger.info(f"Using yt-dlp cookies from browser: {cookies_browser}")
        cmd.insert(1, "--cookies-from-browser")
        cmd.insert(2, cookies_browser)
    
    # 3. Add JS Runtime (for YouTube)
    # Check venv first, then homebrew, then system
    node_found = shutil.which("node")
    if node_found:
        cmd.insert(1, "--js-runtimes")
        cmd.insert(2, f"node:{node_found}")
        cmd.insert(3, "--remote-components")
        cmd.insert(4, "ejs:github")
        
    # 4. Add Proxy
    if proxy:
        cmd.insert(1, "--proxy")
        cmd.insert(2, proxy)

    # 5. Set default format
    cmd.insert(1, "-f")
    cmd.insert(2, "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best")

    return cmd
