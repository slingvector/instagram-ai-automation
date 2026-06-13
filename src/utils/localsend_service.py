import hashlib
import json
import mimetypes
import os
import socket
import struct
import sys
import time
import uuid
import logging
from typing import Optional, Tuple, List

import subprocess
import requests
import urllib3

# Receiver uses a per-device self-signed cert; LAN transfer, so TLS verify is off by design.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("localsend")

class AdbHelper:
    @staticmethod
    def wake_and_launch_localsend(ip: str, port: str = "5555", pin: str = None):
        target = f"{ip}:{port}"
        logger.info(f"ADB Auto-Wake: Connecting to {target}...")
        
        # 1. Connect
        subprocess.run(["adb", "connect", target], capture_output=True, text=True)
        
        # 2. Wake Screen
        logger.info("ADB Auto-Wake: Waking screen...")
        subprocess.run(["adb", "-s", target, "shell", "input", "keyevent", "KEYCODE_WAKEUP"], capture_output=True)
        time.sleep(0.5)
        
        # 3. Dismiss Keyguard (swipe up to reveal PIN pad)
        subprocess.run(["adb", "-s", target, "shell", "wm", "dismiss-keyguard"], capture_output=True)
        time.sleep(0.75)
        
        # 3.5. Type PIN if provided
        if pin:
            logger.info("ADB Auto-Wake: Entering PIN...")
            subprocess.run(["adb", "-s", target, "shell", "input", "text", pin], capture_output=True)
            subprocess.run(["adb", "-s", target, "shell", "input", "keyevent", "KEYCODE_ENTER"], capture_output=True)
            time.sleep(0.75)

        # 4. Launch LocalSend
        logger.info("ADB Auto-Wake: Launching LocalSend app...")
        subprocess.run(["adb", "-s", target, "shell", "am", "start", "-n", "org.localsend.localsend_app/.MainActivity"], capture_output=True)
        
        # 5. Wait for it to bind the port
        logger.info("ADB Auto-Wake: Waiting 1.5 seconds for app to initialize...")
        time.sleep(1.5)

class LocalSendService:
    DEFAULT_PORT = 53317
    MULTICAST_GROUP = "224.0.0.167"
    PROTOCOL_VERSION = "2.1"
    CHUNK = 1024 * 256  # 256 KiB read window for hashing

    SENDER_ALIAS = "ModernOS Relay"
    SENDER_FINGERPRINT = uuid.uuid4().hex  # ignored by receiver in HTTPS mode, but required field

    def __init__(self, target_ip: Optional[str] = None, target_alias: Optional[str] = None, pin: Optional[str] = None):
        self.target_ip = target_ip
        self.target_alias = target_alias
        self.pin = pin
        self.scheme = "https"
        self.port = self.DEFAULT_PORT

    def _sha256_and_size(self, path: str) -> Tuple[str, int]:
        h = hashlib.sha256()
        size = 0
        with open(path, "rb") as f:
            while True:
                block = f.read(self.CHUNK)
                if not block:
                    break
                h.update(block)
                size += len(block)
        return h.hexdigest(), size

    def _file_meta(self, path: str) -> dict:
        sha, size = self._sha256_and_size(path)
        fid = uuid.uuid4().hex
        return {
            "id": fid,
            "fileName": os.path.basename(path),
            "size": size,
            "fileType": mimetypes.guess_type(path)[0] or "application/octet-stream",
            "sha256": sha,
            "_localpath": path,  # internal only, stripped before sending
        }

    def _base_url(self, ip: str, port: int, scheme: str) -> str:
        return f"{scheme}://{ip}:{port}/api/localsend/v2"

    def discover(self, alias_substr: str, timeout: float = 4.0, port: int = DEFAULT_PORT) -> Optional[Tuple[str, str]]:
        """Best-effort multicast discovery. Returns (ip, protocol) for the first device whose
        alias contains `alias_substr`, else None. Falls back to --ip if multicast is blocked."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", port))
        except OSError as e:
            logger.error(f"Cannot bind UDP {port}: {e}")
            return None
        try:
            # Note: macOS routing tables strictly require a default route for the 224.0.0.0/4 subnet.
            # If the routing table lacks this, the kernel will reject the IP_ADD_MEMBERSHIP 
            # or sendto operations with [Errno 65] No route to host (EHOSTUNREACH).
            # Wrapping this in a try/except prevents pipeline crashes when multicast is unroutable.
            mreq = struct.pack("4sl", socket.inet_aton(self.MULTICAST_GROUP), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    
            announce = json.dumps({
                "alias": self.SENDER_ALIAS, "version": "2.0", "deviceType": "headless",
                "fingerprint": self.SENDER_FINGERPRINT, "port": port, "protocol": "https",
                "download": False, "announce": True,
            }).encode()
            sock.sendto(announce, (self.MULTICAST_GROUP, port))
        except OSError as e:
            logger.error(f"Multicast configuration/send failed: {e}. Network might not support UDP multicast.")
            sock.close()
            return None

        sock.settimeout(timeout)
        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                try:
                    data, (src_ip, _) = sock.recvfrom(8192)
                except socket.timeout:
                    break
                try:
                    info = json.loads(data.decode())
                except (ValueError, UnicodeDecodeError):
                    continue
                if alias_substr.lower() in str(info.get("alias", "")).lower():
                    proto = info.get("protocol", "https")
                    logger.info(f"Multicast matched '{info.get('alias')}' at {src_ip} ({proto})")
                    return src_ip, proto
        finally:
            sock.close()
        return None

    def _sender_info(self, scheme: str, port: int) -> dict:
        return {
            "alias": self.SENDER_ALIAS,
            "version": self.PROTOCOL_VERSION,
            "deviceModel": "Pipeline Relay",
            "deviceType": "headless",
            "fingerprint": self.SENDER_FINGERPRINT,
            "port": port,
            "protocol": scheme,
            "download": False,
        }

    def prepare_upload(self, base: str, files: List[dict], scheme: str, port: int,
                       pin: Optional[str], session: requests.Session) -> dict:
        payload = {
            "info": self._sender_info(scheme, port),
            "files": {f["id"]: {k: v for k, v in f.items() if not k.startswith("_")} for f in files},
        }
        params = {"pin": pin} if pin else {}
        r = session.post(f"{base}/prepare-upload", json=payload, params=params,
                         verify=False, timeout=15)
        if r.status_code == 204:
            raise RuntimeError("Receiver reports nothing to transfer (204).")
        if r.status_code == 401:
            raise RuntimeError("PIN required or invalid (401).")
        if r.status_code == 403:
            raise RuntimeError("Rejected by receiver (403). Enable Auto-Accept or accept the prompt.")
        if r.status_code == 409:
            raise RuntimeError("Blocked by another active session (409). Retry shortly.")
        if r.status_code == 429:
            raise RuntimeError("Too many requests (429). Back off and retry.")
        r.raise_for_status()
        body = r.json()
        if "sessionId" not in body or "files" not in body:
            raise RuntimeError(f"Unexpected prepare response: {body}")
        return body

    def upload_file(self, base: str, session_id: str, fid: str, token: str, path: str,
                    session: requests.Session, retries: int = 3) -> None:
        params = {"sessionId": session_id, "fileId": fid, "token": token}
        size = os.path.getsize(path)
        for attempt in range(1, retries + 1):
            try:
                with open(path, "rb") as body:
                    headers = {"Content-Type": "application/octet-stream", "Content-Length": str(size)}
                    r = session.post(f"{base}/upload", params=params, headers=headers,
                                     data=body, verify=False, timeout=600)
                if r.status_code == 200:
                    return
                if r.status_code in (400, 403):
                    raise RuntimeError(f"Fatal {r.status_code} for {os.path.basename(path)}: {r.text}")
                logger.warning(f"Upload {os.path.basename(path)} got {r.status_code}, attempt {attempt}/{retries}")
            except requests.RequestException as e:
                logger.warning(f"Upload {os.path.basename(path)} error: {e} (attempt {attempt}/{retries})")
            time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"Gave up on {os.path.basename(path)} after {retries} attempts.")

    def push(self, paths: List[str]) -> bool:
        """Pushes files to the target. Returns True on success, False on failure."""
        for p in paths:
            if not os.path.isfile(p):
                logger.error(f"Not a file: {p}")
                return False

        ip, scheme = self.target_ip, self.scheme
        
        # Try multicast discovery if IP is not set or we want to resolve by alias
        if self.target_alias:
            found = self.discover(self.target_alias, port=self.port)
            if found:
                ip, scheme = found
            elif not ip:
                logger.error("Multicast discovery failed and no fallback IP given.")
                return False
                
        if not ip:
            logger.error("No target IP or alias configured for LocalSend.")
            return False

        if os.getenv("ADB_ENABLED", "False").lower() in ("true", "1", "yes"):
            adb_port = os.getenv("ADB_PORT", "5555")
            device_pin = os.getenv("DEVICE_PIN", "")
            AdbHelper.wake_and_launch_localsend(ip, adb_port, device_pin)

        base = self._base_url(ip, self.port, scheme)
        files = [self._file_meta(p) for p in paths]
        total = sum(f["size"] for f in files)
        logger.info(f"Relaying -> {ip}:{self.port} ({scheme}) | {len(files)} file(s), {total/1e6:.1f} MB")

        session = requests.Session()
        t0 = time.time()
        
        try:
            prep = self.prepare_upload(base, files, scheme, self.port, self.pin, session)
            session_id, tokens = prep["sessionId"], prep["files"]

            for f in files:
                token = tokens.get(f["id"])
                if not token:
                    logger.warning(f"Receiver skipped {f['fileName']} (no token).")
                    continue
                self.upload_file(base, session_id, f["id"], token, f["_localpath"], session)
                logger.info(f"Delivered {f['fileName']}")

            dt = time.time() - t0
            rate = (total / 1e6) / dt if dt > 0 else 0
            logger.info(f"LocalSend Relay done in {dt:.2f}s ({rate:.1f} MB/s)")
            return True
        except Exception as e:
            logger.error(f"LocalSend transfer failed: {e}")
            return False
