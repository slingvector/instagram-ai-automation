import subprocess
import logging
import time
import re

logger = logging.getLogger(__name__)


class ADBClient:
    """
    Direct ADB shell command wrapper — used as a fast, reliable fallback
    alongside Appium for actions like wake/unlock, launch app, tap coordinates.

    Why: Appium element parsing can be slow or fail on complex Instagram layouts.
    ADB commands bypass the UI hierarchy entirely and are much more stable.
    """

    def __init__(self, device_udid: str = ""):
        self.device_udid = device_udid
        # If udid provided use -s flag, else ADB auto-selects the only connected device
        self._udid_flags = ["-s", device_udid] if device_udid else []
        self._ensure_connected()

    def _ensure_connected(self):
        """If UDID is a TCP/IP address (contains colon), ensure ADB is connected to it."""
        if self.device_udid and ":" in self.device_udid:
            devices = self.list_devices()
            if self.device_udid not in devices:
                logger.info(f"Attempting to auto-connect to wireless device: {self.device_udid}")
                cmd = ["adb", "connect", self.device_udid]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                
                if "connected" in result.stdout.lower():
                    logger.info(f"✅ ADB wirelessly connected to {self.device_udid}")
                else:
                    logger.warning(f"⚠️ ADB wireless connection failed: {result.stdout.strip()}")

    def _run(self, args: list, timeout: int = 15) -> tuple[int, str, str]:
        """Execute an adb command and return (returncode, stdout, stderr)."""
        cmd = ["adb"] + self._udid_flags + args
        logger.debug(f"ADB: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            logger.warning(f"ADB non-zero exit {result.returncode}: {result.stderr.strip()}")
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def wake_screen(self):
        """Turn on screen and dismiss lockscreen via keyevent."""
        self._run(["shell", "input", "keyevent", "KEYCODE_WAKEUP"])
        time.sleep(1.0)
        self._run(["shell", "input", "keyevent", "KEYCODE_MENU"])
        logger.info("Screen woken via ADB.")

    def unlock_device(self, pin: str = None):
        """
        Wakes the screen, swipes up to reveal the PIN pad, and enters the PIN.
        If pin is None, it reads DEVICE_PIN from the environment.
        """
        self.wake_screen()
        
        if not pin:
            import os
            pin = os.getenv("DEVICE_PIN")
            
        if pin:
            logger.info(f"Attempting to unlock device with PIN...")
            # Swipe up from bottom to top to reveal PIN pad
            self.swipe(500, 2000, 500, 500, duration_ms=300)
            time.sleep(1.0)
            
            # Enter PIN
            self.input_text(pin)
            time.sleep(0.5)
            
            # Press Enter
            self._run(["shell", "input", "keyevent", "66"])  # KEYCODE_ENTER
            logger.info("Device unlocked.")
        else:
            logger.info("No DEVICE_PIN set. Assuming device is already unlocked or has no PIN.")

    def press_home(self):
        """Press the Android HOME button."""
        self._run(["shell", "input", "keyevent", "KEYCODE_HOME"])
        logger.info("Home key pressed.")

    def launch_instagram(self, package: str = "com.instagram.android"):
        """Launch Instagram using Android monkey — most reliable cold-start method."""
        self._run([
            "shell", "monkey", "-p", package,
            "-c", "android.intent.category.LAUNCHER", "1"
        ])
        logger.info(f"Launched {package} via monkey.")

    def get_foreground_package(self) -> str:
        """Determines the package name of the application currently in the foreground."""
        # Method 1: dumpsys window (common for newer Android)
        _, stdout, _ = self._run(["shell", "dumpsys", "window", "|", "grep", "-E", "'mCurrentFocus|mFocusedApp'"])
        if stdout:
            # Typical output: mCurrentFocus=Window{... u0 com.instagram.android/com.instagram.mainactivity.MainActivity}
            # Or: mFocusedApp=AppWindowToken{... token=Token{... com.instagram.android/com.instagram.mainactivity.MainActivity}}
            match = re.search(r'([a-zA-Z0-9._]+)/', stdout)
            if match:
                pkg = match.group(1)
                # If there's leading junk before the package (common in some dumps), strip it
                if " " in pkg:
                    pkg = pkg.split(" ")[-1]
                return pkg

        # Method 2: dumpsys activity recents (fallback)
        _, stdout, _ = self._run(["shell", "dumpsys", "activity", "recents", "|", "grep", "'Recent #0'"])
        if stdout:
            match = re.search(r'A=([a-zA-Z0-9._]+)', stdout)
            if match:
                return match.group(1)

        return ""

    def stop_instagram(self, package: str = "com.instagram.android"):
        """Force stop Instagram to start clean."""
        self._run(["shell", "am", "force-stop", package])
        logger.info(f"Force-stopped {package}.")

    def launch_tiktok(self, package: str = "com.zhiliaoapp.musically"):
        """Launch TikTok using Android monkey — most reliable cold-start method."""
        self._run([
            "shell", "monkey", "-p", package,
            "-c", "android.intent.category.LAUNCHER", "1"
        ])
        logger.info(f"Launched {package} via monkey.")

    def launch_youtube(self, package: str = "com.google.android.youtube"):
        """Launch YouTube using Android monkey — most reliable cold-start method."""
        self._run([
            "shell", "monkey", "-p", package,
            "-c", "android.intent.category.LAUNCHER", "1"
        ])
        logger.info(f"Launched {package} via monkey.")

    def tap(self, x: int, y: int):
        """Tap at absolute screen coordinates."""
        self._run(["shell", "input", "tap", str(x), str(y)])

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        """Swipe from (x1,y1) to (x2,y2)."""
        self._run(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)])

    def input_text(self, text: str):
        """Type text via ADB input — escapes spaces for shell."""
        escaped = text.replace(" ", "%s").replace("'", "\\'")
        self._run(["shell", "input", "text", escaped])

    def get_screenshot(self, save_path: str = "/tmp/mcr_screen.png"):
        """Capture screenshot via ADB screencap (faster than Appium's base64 method)."""
        self._run(["shell", "screencap", "-p", "/sdcard/mcr_screen.png"])
        self._run(["pull", "/sdcard/mcr_screen.png", save_path])
        return save_path

    def push_file(self, local_path: str, device_path: str = "/sdcard/Download/"):
        """Push a file to the device (used to stage the processed video)."""
        code, _, err = self._run(["push", local_path, device_path], timeout=60)
        if code != 0:
            raise RuntimeError(f"ADB push failed: {err}")
        dest = device_path + local_path.split("/")[-1] if device_path.endswith("/") else device_path
        logger.info(f"Pushed {local_path} → {dest}")
        
        # Trigger Android Media Scanner so Instagram sees it instantly
        self._run([
            "shell", "am", "broadcast", "-a", 
            "android.intent.action.MEDIA_SCANNER_SCAN_FILE", 
            "-d", f"file://{dest}"
        ])
        
        return dest

    def list_devices(self) -> list[str]:
        """Return list of connected device serial numbers."""
        # Avoid using self._run to prevent -s flag interference
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10)
        devices = []
        for line in result.stdout.splitlines()[1:]:
            if "\tdevice" in line:
                devices.append(line.split("\t")[0])
        return devices
