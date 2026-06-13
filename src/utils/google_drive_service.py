import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

class GoogleDriveService:
    """
    Service to manage Google Drive uploads for manual posting.
    Creates a folder structure: /Industrial Posting/[Date]/[Reel Title]/
    """
    def __init__(self, credentials_path: str = "modernos-edge-agent-key.json", token_path: str = "token.json"):
        self.credentials_path = os.path.abspath(credentials_path)
        self.token_path = os.path.abspath(token_path)
        self.scopes = ['https://www.googleapis.com/auth/drive.file']
        self.service = self._authenticate()
        self.root_folder_name = "Industrial Posting"

    def _authenticate(self):
        import pickle
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
        
        creds = None
        
        # 1. Try OAuth Token (Superior for Personal Drive Quota)
        if os.path.exists(self.token_path):
            try:
                with open(self.token_path, 'rb') as token:
                    creds = pickle.load(token)
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                logger.info("DRIVE: Authenticated using OAuth 2.0 (User Account)")
            except Exception as e:
                logger.warning(f"DRIVE: OAuth token failed: {e}. Falling back to Service Account.")
                creds = None

        # 2. Fallback to Service Account
        if not creds:
            if not os.path.exists(self.credentials_path):
                logger.error(f"DRIVE: Credentials not found at {self.credentials_path}")
                raise FileNotFoundError(f"Credentials not found at {self.credentials_path}")
                
            creds = service_account.Credentials.from_service_account_file(
                self.credentials_path, scopes=self.scopes
            )
            logger.info("DRIVE: Authenticated using Service Account")

        return build('drive', 'v3', credentials=creds)

    def _get_or_create_folder(self, name: str, parent_id: Optional[str] = None) -> str:
        """Finds or creates a folder by name."""
        query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
            
        results = self.service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if files:
            return files[0]['id']
            
        # Create it
        file_metadata: Dict[str, Any] = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]
            
        folder = self.service.files().create(body=file_metadata, fields='id').execute()
        logger.info(f"DRIVE: Created folder '{name}' (ID: {folder['id']})")
        return folder.get('id')

    def upload_reel(self, video_path: str, caption: str, title: str, batch_folder_name: Optional[str] = None) -> str:
        """
        Uploads a video and its caption to a dedicated subfolder on Drive.
        Structure: root / [batch_folder_name or Date] / [Title] / {video, caption.txt}
        Returns the ID of the created reel folder.
        """
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        # 1. Get/Create Root
        root_id = self._get_or_create_folder(self.root_folder_name)
        
        # 2. Get/Create Batch or Date Folder
        target_folder_name = batch_folder_name if batch_folder_name else date_str
        parent_id = self._get_or_create_folder(target_folder_name, parent_id=root_id)
        
        # 3. Create Reel Folder
        reel_folder_id = self._get_or_create_folder(title[:50], parent_id=parent_id)
        
        # 4. Upload Video
        video_file = Path(video_path)
        if video_file.exists():
            media = MediaFileUpload(str(video_file), mimetype='video/mp4', resumable=True)
            file_metadata: Dict[str, Any] = {
                'name': video_file.name,
                'parents': [reel_folder_id]
            }
            uploaded_video = self.service.files().create(
                body=file_metadata, media_body=media, fields='id'
            ).execute()
            logger.info(f"DRIVE: Uploaded video {video_file.name} to Drive.")
        else:
            logger.warning(f"DRIVE: Video file {video_path} not found. Skipping upload.")

        # 5. Upload Caption
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
            tmp.write(caption)
            tmp_path = tmp.name
            
        try:
            media = MediaFileUpload(tmp_path, mimetype='text/plain')
            file_metadata: Dict[str, Any] = {
                'name': 'caption.txt',
                'parents': [reel_folder_id]
            }
            self.service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            logger.info("DRIVE: Uploaded caption.txt to Drive.")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                
        return reel_folder_id

if __name__ == "__main__":
    # Quick Test
    logging.basicConfig(level=logging.INFO)
    try:
        drive = GoogleDriveService()
        print("Drive Service Authenticated!")
    except Exception as e:
        print(f"Auth failed: {e}")
