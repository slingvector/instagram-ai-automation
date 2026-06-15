import subprocess
import requests
import logging
import sqlite3
import os
import shutil
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from google.cloud import firestore, storage
from src.config import GCP_PROJECT_ID, GCS_BUCKET_PROCESSED as GCS_PROCESSED_BUCKET
from src.utils.yt_dlp_helper import get_yt_dlp_command

logger = logging.getLogger(__name__)

class PreFlightDiagnostic:
    def __init__(self):
        self.results = {}



    def check_gcp(self):
        """Verify Firestore and GCS bucket access with retries."""
        max_retries = 3
        gcp_status = []
        
        # Firestore Check
        for i in range(max_retries):
            try:
                db = firestore.Client(project=GCP_PROJECT_ID)
                list(db.collections(timeout=5))
                gcp_status.append("Firestore OK")
                break
            except Exception as e:
                if i == max_retries - 1:
                    return ('GCP', (False, f"Firestore Failed after {max_retries} attempts: {e}"))
                time.sleep(1)

        # GCS Check
        for i in range(max_retries):
            try:
                storage_client = storage.Client(project=GCP_PROJECT_ID)
                bucket = storage_client.bucket(GCS_PROCESSED_BUCKET)
                if bucket.exists(timeout=5):
                    gcp_status.append("GCS OK")
                    break
                else:
                    gcp_status.append(f"GCS Bucket {GCS_PROCESSED_BUCKET} not found")
                    break
            except Exception as e:
                if i == max_retries - 1:
                    return ('GCP', (False, f"GCS Failed after {max_retries} attempts: {e}"))
                time.sleep(1)
        
        return ('GCP', (True, " | ".join(gcp_status)))

    def check_dependencies(self):
        """Verify yt-dlp and ffmpeg are in PATH."""
        deps = []
        # yt-dlp detection
        venv_bin = Path(sys.executable).parent
        venv_yt = venv_bin / "yt-dlp"
        
        if venv_yt.exists():
            deps.append("yt-dlp OK (venv)")
        elif shutil.which("yt-dlp"):
            deps.append("yt-dlp OK (system)")
        else:
            deps.append("yt-dlp MISSING")
            
        # ffmpeg
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
            deps.append("ffmpeg OK")
        except Exception:
            deps.append("ffmpeg MISSING")
            
        success = all("OK" in d for d in deps)
        return ('Dependencies', (success, " | ".join(deps)))

    def check_database(self):
        """Verify local SQLite state database."""
        db_path = "data/bulk_post_state.db"
        try:
            if not os.path.exists(db_path):
                return ('Database', (False, f"Database not found at {db_path}"))
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            conn.close()
            return ('Database', (True, f"SQLite Healthy ({len(tables)} tables)"))
        except Exception as e:
            return ('Database', (False, f"DB Error: {str(e)}"))

    def check_docker(self):
        """Verify Docker daemon and critical MCR containers."""
        if not shutil.which("docker"):
            return ('Docker', (False, "Docker CLI not found in PATH"))
            
        try:
            # Check if daemon is running
            subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5, check=True)
            
            containers_to_check = ["mcr-ingestion"]
                
            status_parts = ["Daemon OK"]
            
            # Use docker ps to check for running containers
            cmd = ["docker", "ps", "--format", "{{.Names}}:{{.Status}}"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            running_containers = {line.split(':')[0]: line.split(':')[1] for line in result.stdout.strip().split('\n') if ':' in line}
            
            for container in containers_to_check:
                if container in running_containers:
                    status_parts.append(f"{container} OK")
                else:
                    # Don't fail the whole check if containers aren't running yet, 
                    # but report it. bulk_post might be starting them.
                    status_parts.append(f"{container} NOT RUNNING")
            
            return ('Docker', (True, " | ".join(status_parts)))
        except subprocess.CalledProcessError:
            return ('Docker', (False, "Docker daemon not reachable (is Docker Desktop running?)"))
        except Exception as e:
            return ('Docker', (False, f"Docker Error: {str(e)}"))

    def run_all(self):
        """Run all diagnostic checks in parallel."""
        checks = [
            self.check_docker,
            self.check_gcp,
            self.check_dependencies,
            self.check_database
        ]
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_check = {executor.submit(check): check for check in checks}
            for future in as_completed(future_to_check):
                name, result = future.result()
                self.results[name] = result
                
        return self.results
