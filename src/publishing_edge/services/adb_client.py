import subprocess
import logging
import time

logger = logging.getLogger(__name__)


class ADBClient:
    """
    Direct ADB shell command wrapper — used as a fast, reliable fallback
    alongside Appium for actions like wake/unlock, launch app, tap coordinates.

    Why: Appium element parsing can be slow or fail on complex Instagram layouts.
    ADB commands bypass the UI hierarchy entirely and are much more stable.
    """

    def __init__(self, device_udid: str = ""):
        # If udid provided use -s flag, else ADB auto-selects the only connected device
        self._udid_flags = ["-s", device_udid] if device_udid else []

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
        time.sleep(0.5)
        self._run(["shell", "input", "keyevent", "KEYCODE_MENU"])
        logger.info("Screen woken via ADB.")

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

    def stop_instagram(self, package: str = "com.instagram.android"):
        """Force stop Instagram to start clean."""
        self._run(["shell", "am", "force-stop", package])
        logger.info(f"Force-stopped {package}.")

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
        _, stdout, _ = self._run(["devices"])
        devices = []
        for line in stdout.splitlines()[1:]:
            if "\tdevice" in line:
                devices.append(line.split("\t")[0])
        return devices
