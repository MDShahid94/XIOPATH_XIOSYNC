"""
Google Drive Sync for Colab Worker Profiles
============================================
Upload and download encrypted .xio Chrome profiles to/from Google Drive.

In Colab: Uses google.colab.auth for authentication (zero-config)
Outside Colab: Uses service account JSON credentials

Profile persistence flow:
    Boot:     Drive → download .xio → decrypt → Chrome profile
    Periodic: Chrome profile → encrypt → .xio → upload to Drive
    Shutdown: Final profile save → upload to Drive
"""

import os
import io
import logging
from typing import Optional

logger = logging.getLogger("DriveSync")


class DriveSync:
    """
    Handles encrypted profile blob upload/download to Google Drive.

    Supports both Colab-native authentication (google.colab.auth)
    and service account credentials for non-Colab environments.
    """

    def __init__(
        self,
        folder_id: str,
        service_account_path: Optional[str] = None,
    ):
        """
        Args:
            folder_id: Google Drive folder ID where profiles are stored
            service_account_path: Path to service account JSON (non-Colab only)
        """
        self.folder_id = folder_id
        self.service_account_path = service_account_path
        self._drive_service = None

    @property
    def drive(self):
        """Lazy-init Drive API service."""
        if self._drive_service is None:
            self._drive_service = self._authenticate()
        return self._drive_service

    def _authenticate(self):
        """Authenticate with Drive API."""
        from googleapiclient.discovery import build

        is_colab = "COLAB_RELEASE_TAG" in os.environ or "COLAB_GPU" in os.environ

        if is_colab:
            logger.info("Authenticating via Colab auth...")
            from google.colab import auth
            auth.authenticate_user()
            from google.auth import default
            creds, _ = default()
        elif self.service_account_path:
            logger.info(f"Authenticating via service account: {self.service_account_path}")
            from google.oauth2.service_account import Credentials
            creds = Credentials.from_service_account_file(self.service_account_path)
        else:
            raise RuntimeError(
                "Not in Colab and no service_account_path provided. "
                "Cannot authenticate with Drive API."
            )

        return build("drive", "v3", credentials=creds)

    # ================================================================
    # DOWNLOAD
    # ================================================================

    def download_profile(self, file_name: str) -> Optional[bytes]:
        """
        Download an encrypted .xio profile from Drive.

        Args:
            file_name: Name of the file in the Drive folder (e.g., "worker_1.xio")

        Returns:
            Raw encrypted bytes, or None if file not found
        """
        logger.info(f"Searching for '{file_name}' in folder {self.folder_id}...")

        try:
            results = self.drive.files().list(
                q=f"'{self.folder_id}' in parents and name='{file_name}'",
                spaces="drive",
                fields="files(id, name, size)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()

            items = results.get("files", [])
            if not items:
                logger.info(f"No file '{file_name}' found in Drive folder.")
                return None

            file_id = items[0]["id"]
            file_size = items[0].get("size", "?")
            logger.info(f"Found '{file_name}' ({file_size} bytes). Downloading...")

            from googleapiclient.http import MediaIoBaseDownload

            request = self.drive.files().get_media(fileId=file_id)
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(f"Download progress: {int(status.progress() * 100)}%")

            data = buffer.getvalue()
            logger.info(f"Downloaded '{file_name}' ({len(data)} bytes).")
            return data

        except Exception as e:
            logger.error(f"Drive download failed: {e}")
            return None

    # ================================================================
    # UPLOAD
    # ================================================================

    def upload_profile(self, file_name: str, data: bytes) -> Optional[str]:
        """
        Upload an encrypted .xio profile to Drive (overwrite if exists).

        Args:
            file_name: Target filename in Drive (e.g., "worker_1.xio")
            data: Encrypted .xio bytes to upload

        Returns:
            Drive file ID on success, None on failure
        """
        logger.info(f"Uploading '{file_name}' ({len(data)} bytes) to Drive...")

        try:
            from googleapiclient.http import MediaInMemoryUpload

            # Check if file already exists (to overwrite)
            existing = self.drive.files().list(
                q=f"'{self.folder_id}' in parents and name='{file_name}'",
                spaces="drive",
                fields="files(id)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute().get("files", [])

            media = MediaInMemoryUpload(data, resumable=True)

            if existing:
                # Overwrite existing file
                file_id = existing[0]["id"]
                updated = self.drive.files().update(
                    fileId=file_id,
                    media_body=media,
                    supportsAllDrives=True,
                ).execute()
                logger.info(f"Updated existing file '{file_name}' (ID: {file_id})")
                return file_id
            else:
                # Create new file
                file_metadata = {
                    "name": file_name,
                    "parents": [self.folder_id],
                }
                created = self.drive.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id",
                    supportsAllDrives=True,
                ).execute()
                file_id = created.get("id")
                logger.info(f"Created new file '{file_name}' (ID: {file_id})")
                return file_id

        except Exception as e:
            logger.error(f"Drive upload failed: {e}")
            return None

    # ================================================================
    # VAULT KEY SYNC
    # ================================================================

    def download_vault_key(self, key_name: str = ".vault_key") -> Optional[bytes]:
        """Download the shared vault key from Drive (for multi-node encryption)."""
        return self.download_profile(key_name)

    def upload_vault_key(self, key_data: bytes, key_name: str = ".vault_key") -> Optional[str]:
        """Upload vault key to Drive for sharing across worker nodes."""
        return self.upload_profile(key_name, key_data)
