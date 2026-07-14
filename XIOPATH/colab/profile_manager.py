"""
Encrypted Chrome Profile Manager for Colab Worker Bots
======================================================
Handles Chrome profile load/save with Fernet encryption (.xio format).

Ported from XIO_VERSE ProfileManager + SecurityModule, integrated with
XIOPATH's existing SecretManager for shared vault key.

Profile lifecycle:
    1. Download .xio from Drive (see drive_sync.py)
    2. Decrypt → extract to temp directory
    3. Trim bloat (Cache, Service Workers, etc.)
    4. Pass path to StealthBrowser
    5. On save: trim → zip → encrypt → return .xio bytes
"""

import os
import shutil
import glob
import logging
from typing import Tuple, Optional

from cryptography.fernet import Fernet

logger = logging.getLogger("ColabProfileManager")


class ColabProfileManager:
    """
    Manages encrypted Chrome profiles (.xio) for ephemeral Colab environments.

    Uses Fernet symmetric encryption (same as XIOPATH's SecretManager)
    so the same vault key can encrypt both API secrets and Chrome profiles.
    """

    # Directories that are safe to delete (bloat)
    BLOAT_TARGETS = [
        "Cache", "Code Cache", "Service Worker", "DawnCache",
        "GPUCache", "Crashpad", "SingletonLock", "SingletonCookie",
        "SingletonSocket", "ScriptCache",
    ]

    # Essential files to keep in slim mode (session persistence)
    ESSENTIAL_TARGETS = [
        "Cookies", "Web Data", "Local Storage", "Sessions",
        "Network Action Predictor",
    ]

    def __init__(
        self,
        profiles_dir: str = "/content/profiles",
        temp_dir: Optional[str] = None,
        vault_key_path: Optional[str] = None,
    ):
        self.profiles_dir = profiles_dir
        self.temp_dir = temp_dir or os.path.join(profiles_dir, "_temp")
        os.makedirs(self.profiles_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

        # Initialize Fernet encryption
        self.vault_key_path = vault_key_path or os.path.join(
            self.profiles_dir, ".vault_key"
        )
        self.fernet = self._init_fernet()

    def _init_fernet(self) -> Fernet:
        """Load or generate Fernet key, compatible with SecretManager."""
        os.makedirs(os.path.dirname(self.vault_key_path), exist_ok=True)

        if os.path.exists(self.vault_key_path):
            with open(self.vault_key_path, "rb") as f:
                key = f.read().strip()
        else:
            key = Fernet.generate_key()
            with open(self.vault_key_path, "wb") as f:
                f.write(key)
            logger.info(f"Generated new vault key at {self.vault_key_path}")

        return Fernet(key)

    # ================================================================
    # ENCRYPTION
    # ================================================================

    def encrypt_bytes(self, data: bytes) -> bytes:
        """Encrypt raw bytes with Fernet."""
        if not data:
            return b""
        return self.fernet.encrypt(data)

    def decrypt_bytes(self, data: bytes) -> bytes:
        """Decrypt Fernet-encrypted bytes."""
        if not data:
            return b""
        try:
            return self.fernet.decrypt(data)
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return b""

    # ================================================================
    # PROFILE TRIMMING
    # ================================================================

    def trim_profile(self, local_dir: str, essential_only: bool = False):
        """
        Remove Chrome profile bloat before saving.

        Args:
            essential_only: If True, keeps only session-critical files
                           (Cookies, Sessions, LocalStorage). Much smaller.
        """
        logger.info(
            f"Trimming profile ({'essential-only' if essential_only else 'standard'})..."
        )

        if essential_only:
            for root, dirs, files in os.walk(local_dir, topdown=False):
                for d in dirs:
                    if d not in self.ESSENTIAL_TARGETS and "Extension" not in d:
                        try:
                            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                        except Exception:
                            pass
                for f in files:
                    if not any(k in f for k in self.ESSENTIAL_TARGETS):
                        try:
                            os.remove(os.path.join(root, f))
                        except Exception:
                            pass
        else:
            for root, dirs, files in os.walk(local_dir):
                for d in dirs:
                    if d in self.BLOAT_TARGETS:
                        try:
                            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                        except Exception:
                            pass
                for f in files:
                    if f in self.BLOAT_TARGETS:
                        try:
                            os.remove(os.path.join(root, f))
                        except Exception:
                            pass

    # ================================================================
    # LOAD PROFILE
    # ================================================================

    def load_profile(self, profile_id: str, xio_bytes: Optional[bytes] = None) -> str:
        """
        Load a Chrome profile for use.

        Args:
            profile_id: Identifier for this profile (e.g., "colab_worker_1")
            xio_bytes: Raw encrypted .xio bytes (from Drive). If None, checks
                      local profiles_dir for existing .xio files.

        Returns:
            Path to the extracted profile directory, ready for Chrome --user-data-dir
        """
        extract_path = os.path.join(self.temp_dir, profile_id)

        if xio_bytes:
            # Decrypt and extract from provided bytes
            logger.info(f"Decrypting profile '{profile_id}' from .xio blob...")
            try:
                zip_bytes = self.decrypt_bytes(xio_bytes)
                if not zip_bytes:
                    raise ValueError("Decryption returned empty payload")

                zip_path = os.path.join(self.temp_dir, f"{profile_id}.zip")
                with open(zip_path, "wb") as f:
                    f.write(zip_bytes)

                shutil.rmtree(extract_path, ignore_errors=True)
                shutil.unpack_archive(zip_path, extract_path, "zip")
                os.remove(zip_path)
                logger.info(f"Profile '{profile_id}' restored from encrypted blob.")

            except Exception as e:
                logger.warning(f"Failed to restore profile: {e}. Starting fresh.")
                shutil.rmtree(extract_path, ignore_errors=True)
                os.makedirs(extract_path, exist_ok=True)
        else:
            # Check local .xio files
            xio_files = glob.glob(
                os.path.join(self.profiles_dir, f"{profile_id}*.xio")
            )
            if xio_files:
                logger.info(f"Found local .xio: {xio_files[0]}")
                with open(xio_files[0], "rb") as f:
                    return self.load_profile(profile_id, f.read())
            else:
                logger.info(f"No profile found for '{profile_id}'. Starting fresh.")
                shutil.rmtree(extract_path, ignore_errors=True)
                os.makedirs(extract_path, exist_ok=True)

        self.trim_profile(extract_path)
        return extract_path

    # ================================================================
    # SAVE PROFILE
    # ================================================================

    def save_profile(
        self,
        extract_path: str,
        profile_id: str,
        essential_only: bool = False,
        encrypt: bool = True,
    ) -> bytes:
        """
        Save and encrypt a Chrome profile to .xio format.

        Args:
            extract_path: Path to the live Chrome profile directory
            profile_id: Profile identifier
            essential_only: Trim to minimal session files only
            encrypt: Whether to encrypt (True for production, False for debugging)

        Returns:
            Encrypted .xio bytes ready for Drive upload, or raw zip bytes if encrypt=False
        """
        try:
            # 1. Trim
            self.trim_profile(extract_path, essential_only=essential_only)

            # 2. Zip
            zip_path = os.path.join(self.temp_dir, profile_id)
            shutil.make_archive(zip_path, "zip", extract_path)
            zip_file = f"{zip_path}.zip"

            with open(zip_file, "rb") as f:
                raw_bytes = f.read()

            os.remove(zip_file)

            if not encrypt:
                # Save as plain .zip locally
                local_path = os.path.join(self.profiles_dir, f"{profile_id}.zip")
                with open(local_path, "wb") as f:
                    f.write(raw_bytes)
                logger.info(f"Profile saved as .zip ({local_path})")
                return raw_bytes

            # 3. Encrypt
            enc_bytes = self.encrypt_bytes(raw_bytes)
            if not enc_bytes:
                raise ValueError("Encryption returned empty payload")

            # Save locally as .xio
            xio_path = os.path.join(self.profiles_dir, f"{profile_id}.xio")
            with open(xio_path, "wb") as f:
                f.write(enc_bytes)

            logger.info(
                f"Profile saved as encrypted .xio "
                f"({len(enc_bytes)} bytes → {xio_path})"
            )
            return enc_bytes

        except Exception as e:
            logger.error(f"Failed to save profile: {e}")
            return b""
