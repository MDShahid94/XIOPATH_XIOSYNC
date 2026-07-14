import json
import time
import os
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Attempt to use Fernet encryption; fall back to plaintext if cryptography not installed
try:
    from cryptography.fernet import Fernet
    HAS_ENCRYPTION = True
except ImportError:
    HAS_ENCRYPTION = False
    logger.warning("cryptography package not installed. API keys will be stored in PLAINTEXT.")


class ApiManager:
    """
    Manages API key rotation with cooldown tracking.
    Stores keys encrypted at rest using Fernet symmetric encryption.
    """
    def __init__(self, keys_file: str = "data/api_keys.json", key_file: str = "data/.vault_key"):
        self.keys_file = Path(keys_file)
        self.key_path = Path(key_file)
        self.keys: List[Dict] = []
        self._fernet: Optional[object] = None
        self._rotation_index: int = 0   # F-15: Round-robin counter
        self._save_counter: int = 0     # F-16: Batched save counter
        self._SAVE_INTERVAL: int = 10   # F-16: Save every N token updates

        if HAS_ENCRYPTION:
            self._init_encryption()

        self._load_keys()

    def _init_encryption(self):
        """Initialize encryption using a derived key for API key domain isolation (Phase 23: S-09)."""
        if not self.key_path.parent.exists():
            self.key_path.parent.mkdir(parents=True, exist_ok=True)

        if self.key_path.exists():
            key = self.key_path.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            self.key_path.write_bytes(key)
            os.chmod(self.key_path, 0o600)
            logger.info("Generated new vault encryption key.")

        # Derive a domain-specific key so API key encryption is isolated from secrets
        import hashlib, base64
        derived = hashlib.sha256(key + b"::api_keys_domain_v1").digest()
        derived_key = base64.urlsafe_b64encode(derived)
        self._fernet = Fernet(derived_key)

    def _encrypt(self, data: str) -> bytes:
        if self._fernet:
            return self._fernet.encrypt(data.encode('utf-8'))
        return data.encode('utf-8')

    def _decrypt(self, data: bytes) -> str:
        if self._fernet:
            try:
                return self._fernet.decrypt(data).decode('utf-8')
            except Exception:
                # Likely a plaintext file — auto-migrate
                try:
                    plaintext = data.decode('utf-8')
                    json.loads(plaintext)
                    logger.info("Auto-migrating plaintext API keys to encrypted format.")
                    self._save_keys_internal(json.loads(plaintext))
                    return plaintext
                except (UnicodeDecodeError, json.JSONDecodeError):
                    logger.error("Failed to decrypt API keys.")
                    return "[]"
        return data.decode('utf-8')

    def _load_keys(self):
        if self.keys_file.exists():
            try:
                raw = self.keys_file.read_bytes()
                text = self._decrypt(raw)
                self.keys = json.loads(text)
            except Exception as e:
                logger.error(f"Failed to load API keys: {e}")
                self.keys = []
        else:
            self.keys = []
            
    def _save_keys_internal(self, keys_data):
        """Write keys to encrypted file."""
        encrypted = self._encrypt(json.dumps(keys_data, indent=4))
        self.keys_file.parent.mkdir(parents=True, exist_ok=True)
        self.keys_file.write_bytes(encrypted)

    def _save_keys(self):
        self._save_keys_internal(self.keys)

    def add_key(self, api_key: str):
        """Add a new API key to the rotation pool."""
        if not any(k["key"] == api_key for k in self.keys):
            self.keys.append({
                "key": api_key,
                "status": "active",
                "cooling_until": 0,
                "tokens_used": 0
            })
            self._save_keys()
            logger.info(f"Added new API key ending in ...{api_key[-4:]}")

    def get_next_key(self) -> str:
        """Returns the next available active key using round-robin rotation (F-15)."""
        current_time = time.time()
        n = len(self.keys)
        if n == 0:
            raise Exception("No API keys configured!")
        
        for i in range(n):
            idx = (self._rotation_index + i) % n
            k = self.keys[idx]
            if k["status"] == "active":
                self._rotation_index = (idx + 1) % n
                return k["key"]
            if k["status"] == "cooling" and current_time > k["cooling_until"]:
                k["status"] = "active"
                self._save_keys()
                logger.info(f"API key ...{k['key'][-4:]} cooldown expired, reactivated.")
                self._rotation_index = (idx + 1) % n
                return k["key"]
                
        raise Exception("No active or cooled-down API keys available!")

    def mark_cooling(self, api_key: str, reason: str = ""):
        """Dynamically mark a key as cooling down based on the error reason."""
        current_time = time.time()
        
        # Free tier Gemini limits: 15 RPM (minute), 1500 RPD (day)
        if "quota" in reason.lower() or "day" in reason.lower():
            cooldown_seconds = 86400  # 24 hours
        else:
            cooldown_seconds = 60
            
        for k in self.keys:
            if k["key"] == api_key:
                k["status"] = "cooling"
                k["cooling_until"] = current_time + cooldown_seconds
                self._save_keys()
                logger.warning(f"API key ...{api_key[-4:]} cooling for {cooldown_seconds}s. Reason: {reason}")
                break

    def mark_expired(self, api_key: str):
        for k in self.keys:
            if k["key"] == api_key:
                k["status"] = "expired"
                self._save_keys()
                logger.warning(f"API key ...{api_key[-4:]} marked as expired.")
                break

    def update_tokens(self, api_key: str, tokens: int):
        """Track token usage with batched disk saves (F-16)."""
        for k in self.keys:
            if k["key"] == api_key:
                k["tokens_used"] = k.get("tokens_used", 0) + tokens
                self._save_counter += 1
                if self._save_counter >= self._SAVE_INTERVAL:
                    self._save_keys()
                    self._save_counter = 0
                break

    def flush(self):
        """Force save current key state to disk (call on shutdown)."""
        if self._save_counter > 0:
            self._save_keys()
            self._save_counter = 0

    def get_status_report(self) -> str:
        report = "API Keys Status:\n"
        for i, k in enumerate(self.keys):
            masked_key = k["key"][:8] + "..." + k["key"][-4:]
            status = k["status"]
            tokens = k.get("tokens_used", 0)
            if status == "cooling":
                rem = int(k["cooling_until"] - time.time())
                report += f"[{i+1}] {masked_key} - COOLING ({rem}s left) - Tokens: {tokens}\n"
            else:
                report += f"[{i+1}] {masked_key} - {status.upper()} - Tokens: {tokens}\n"
        return report
