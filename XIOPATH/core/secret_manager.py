import json
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Attempt to use Fernet encryption; fall back to plaintext if cryptography not installed
try:
    from cryptography.fernet import Fernet
    HAS_ENCRYPTION = True
except ImportError:
    HAS_ENCRYPTION = False
    logger.warning("cryptography package not installed. Secrets will be stored in PLAINTEXT. "
                   "Install with: pip install cryptography")


class SecretManager:
    """
    Manages local secrets using a JSON keystore with optional Fernet encryption at rest.
    Automatically migrates plaintext files to encrypted format on first access.
    """
    def __init__(self, secrets_file: str = "data/secrets.json", key_file: str = "data/.vault_key"):
        self.secrets_path = Path(secrets_file)
        self.key_path = Path(key_file)
        self._fernet: Optional[object] = None

        if HAS_ENCRYPTION:
            self._init_encryption()
        
        self._ensure_exists()

    def _init_encryption(self):
        """Initialize encryption using a derived key for secrets domain isolation (Phase 23: S-09)."""
        if not self.key_path.parent.exists():
            self.key_path.parent.mkdir(parents=True, exist_ok=True)

        if self.key_path.exists():
            key = self.key_path.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            self.key_path.write_bytes(key)
            # Restrict file permissions (owner-only read/write)
            os.chmod(self.key_path, 0o600)
            logger.info("Generated new vault encryption key.")

        # Derive a domain-specific key so secrets encryption is isolated from API keys
        import hashlib, base64
        derived = hashlib.sha256(key + b"::secrets_domain_v1").digest()
        derived_key = base64.urlsafe_b64encode(derived)
        self._fernet = Fernet(derived_key)

    def _encrypt(self, data: str) -> bytes:
        """Encrypt a string and return bytes."""
        if self._fernet:
            return self._fernet.encrypt(data.encode('utf-8'))
        return data.encode('utf-8')

    def _decrypt(self, data: bytes) -> str:
        """Decrypt bytes and return string. Falls back to plaintext if decryption fails."""
        if self._fernet:
            try:
                return self._fernet.decrypt(data).decode('utf-8')
            except Exception:
                # Likely a plaintext file from before encryption was enabled — auto-migrate
                try:
                    plaintext = data.decode('utf-8')
                    json.loads(plaintext)  # Validate it's valid JSON
                    logger.info("Auto-migrating plaintext secrets to encrypted format.")
                    self._write_encrypted(plaintext)
                    return plaintext
                except (UnicodeDecodeError, json.JSONDecodeError):
                    logger.error("Failed to decrypt secrets and plaintext migration failed.")
                    return "{}"
        return data.decode('utf-8')

    def _read_decrypted(self) -> dict:
        """Read and decrypt the secrets file."""
        try:
            raw = self.secrets_path.read_bytes()
            text = self._decrypt(raw)
            return json.loads(text)
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.error(f"Error reading secrets: {e}")
            return {}

    def _write_encrypted(self, json_str: str):
        """Write encrypted data to the secrets file."""
        encrypted = self._encrypt(json_str)
        self.secrets_path.write_bytes(encrypted)

    def _ensure_exists(self):
        if not self.secrets_path.parent.exists():
            self.secrets_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.secrets_path.exists():
            self._write_encrypted(json.dumps({}))
                
    def get_secret(self, key: str) -> str:
        """Retrieves a secret by key. Returns empty string if not found."""
        secrets = self._read_decrypted()
        return secrets.get(key, "")
            
    def set_secret(self, key: str, value: str):
        """Sets a secret in the encrypted keystore."""
        try:
            secrets = self._read_decrypted()
            secrets[key] = value
            self._write_encrypted(json.dumps(secrets, indent=4))
            logger.info(f"Secret '{key}' saved successfully.")
        except Exception as e:
            logger.error(f"Error setting secret '{key}': {e}")
            
    def list_keys(self) -> list:
        """Returns a list of all secret keys without revealing their values."""
        secrets = self._read_decrypted()
        return list(secrets.keys())

    def delete_secret(self, key: str):
        """Deletes a secret from the encrypted keystore."""
        try:
            secrets = self._read_decrypted()
            if key in secrets:
                del secrets[key]
                self._write_encrypted(json.dumps(secrets, indent=4))
                logger.info(f"Secret '{key}' deleted successfully.")
        except Exception as e:
            logger.error(f"Error deleting secret '{key}': {e}")
            raise
