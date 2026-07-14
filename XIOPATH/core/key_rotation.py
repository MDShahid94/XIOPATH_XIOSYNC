"""
Enterprise Vault Key Rotation Utility (Phase 23: S-10)
========================================================

Rotates the master vault key and re-encrypts all data files using the
domain-separated key derivation scheme.

Usage:
    python -m core.key_rotation rotate          # Rotate and re-encrypt
    python -m core.key_rotation verify          # Verify all files are readable
    python -m core.key_rotation rollback        # Rollback to previous key

After rotation:
    - Old key is backed up to data/.vault_key.bak
    - All encrypted files are re-encrypted with the new key
    - Verify with `python -m core.key_rotation verify` before deleting backup
"""

import os
import sys
import json
import shutil
import logging
import hashlib
import base64
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

try:
    from cryptography.fernet import Fernet, InvalidToken
    HAS_ENCRYPTION = True
except ImportError:
    HAS_ENCRYPTION = False


# Domain tags must match those in api_manager.py and secret_manager.py
DOMAIN_TAGS = {
    "data/api_keys.json": b"::api_keys_domain_v1",
    "data/secrets.json": b"::secrets_domain_v1",
}


def _derive_fernet(master_key: bytes, domain_tag: bytes) -> 'Fernet':
    """Derive a domain-specific Fernet instance from the master key."""
    derived = hashlib.sha256(master_key + domain_tag).digest()
    derived_key = base64.urlsafe_b64encode(derived)
    return Fernet(derived_key)


def _try_decrypt(fernet: 'Fernet', raw: bytes) -> Tuple[bool, Optional[str]]:
    """Attempt to decrypt data. Returns (success, plaintext_or_None)."""
    try:
        plaintext = fernet.decrypt(raw).decode('utf-8')
        json.loads(plaintext)  # Validate JSON
        return True, plaintext
    except (InvalidToken, Exception):
        return False, None


def rotate(
    vault_key_path: str = "data/.vault_key",
    data_files: Optional[List[str]] = None,
):
    """
    Rotate the vault key: generate new key, re-encrypt all data files.
    
    Steps:
        1. Read current master key
        2. Decrypt all data files with old domain-derived keys
        3. Generate new master key
        4. Re-encrypt all data files with new domain-derived keys
        5. Write new key, backup old key
    """
    if not HAS_ENCRYPTION:
        logger.error("cryptography package not installed. Cannot rotate keys.")
        return False

    if data_files is None:
        data_files = list(DOMAIN_TAGS.keys())

    key_path = Path(vault_key_path)
    if not key_path.exists():
        logger.error(f"Vault key not found: {vault_key_path}")
        return False

    old_key = key_path.read_bytes().strip()
    logger.info("Read current master key.")

    # Phase 1: Decrypt all files with old key
    decrypted_data = {}
    for file_str in data_files:
        file_path = Path(file_str)
        if not file_path.exists():
            logger.warning(f"Skipping missing file: {file_path}")
            continue

        raw = file_path.read_bytes()
        domain_tag = DOMAIN_TAGS.get(file_str, b"::unknown_domain")
        old_fernet = _derive_fernet(old_key, domain_tag)

        success, plaintext = _try_decrypt(old_fernet, raw)
        if success:
            decrypted_data[file_str] = plaintext
            logger.info(f"Decrypted: {file_path}")
        else:
            # Try raw Fernet (pre-domain-separation migration)
            try:
                old_raw_fernet = Fernet(old_key)
                plaintext = old_raw_fernet.decrypt(raw).decode('utf-8')
                json.loads(plaintext)
                decrypted_data[file_str] = plaintext
                logger.info(f"Decrypted (legacy non-derived key): {file_path}")
            except Exception:
                # Maybe it's plaintext
                try:
                    plaintext = raw.decode('utf-8')
                    json.loads(plaintext)
                    decrypted_data[file_str] = plaintext
                    logger.info(f"File is plaintext: {file_path}")
                except Exception:
                    logger.error(f"Cannot decrypt or read: {file_path}. Aborting rotation.")
                    return False

    # Phase 2: Generate new master key
    new_key = Fernet.generate_key()
    logger.info("Generated new master key.")

    # Phase 3: Re-encrypt all files with new key
    for file_str, plaintext in decrypted_data.items():
        file_path = Path(file_str)
        domain_tag = DOMAIN_TAGS.get(file_str, b"::unknown_domain")
        new_fernet = _derive_fernet(new_key, domain_tag)
        encrypted = new_fernet.encrypt(plaintext.encode('utf-8'))
        file_path.write_bytes(encrypted)
        logger.info(f"Re-encrypted: {file_path}")

    # Phase 4: Backup old key and write new key
    backup_path = key_path.with_suffix('.vault_key.bak')
    shutil.copy2(key_path, backup_path)
    os.chmod(backup_path, 0o600)
    logger.info(f"Old key backed up to: {backup_path}")

    key_path.write_bytes(new_key)
    os.chmod(key_path, 0o600)
    logger.info("New master key written.")

    print("\n✅ Vault key rotated successfully!")
    print(f"   Old key backup: {backup_path}")
    print(f"   Run 'python -m core.key_rotation verify' to confirm.")
    print(f"   Delete {backup_path} after verification.")
    return True


def verify(vault_key_path: str = "data/.vault_key", data_files: Optional[List[str]] = None):
    """Verify all encrypted files are readable with the current key."""
    if not HAS_ENCRYPTION:
        logger.error("cryptography package not installed.")
        return False

    if data_files is None:
        data_files = list(DOMAIN_TAGS.keys())

    key_path = Path(vault_key_path)
    if not key_path.exists():
        logger.error(f"Vault key not found: {vault_key_path}")
        return False

    key = key_path.read_bytes().strip()
    all_ok = True

    for file_str in data_files:
        file_path = Path(file_str)
        if not file_path.exists():
            print(f"  ⚠️  {file_path} — not found (skipped)")
            continue

        raw = file_path.read_bytes()
        domain_tag = DOMAIN_TAGS.get(file_str, b"::unknown_domain")
        fernet = _derive_fernet(key, domain_tag)

        success, plaintext = _try_decrypt(fernet, raw)
        if success:
            data = json.loads(plaintext)
            count = len(data) if isinstance(data, (dict, list)) else "N/A"
            print(f"  ✅ {file_path} — OK ({count} entries)")
        else:
            print(f"  ❌ {file_path} — FAILED to decrypt")
            all_ok = False

    if all_ok:
        print("\n✅ All files verified successfully.")
    else:
        print("\n❌ Some files failed verification. Check logs above.")
    return all_ok


def rollback(vault_key_path: str = "data/.vault_key"):
    """Rollback to the previous vault key from backup."""
    key_path = Path(vault_key_path)
    backup_path = key_path.with_suffix('.vault_key.bak')

    if not backup_path.exists():
        logger.error(f"No backup key found at {backup_path}")
        return False

    # Swap: current → .vault_key.new, backup → current
    new_backup = key_path.with_suffix('.vault_key.new')
    shutil.copy2(key_path, new_backup)
    shutil.copy2(backup_path, key_path)
    os.chmod(key_path, 0o600)

    print(f"✅ Rolled back to previous key.")
    print(f"   Current (rolled back) key: {key_path}")
    print(f"   New key (saved as): {new_backup}")
    print(f"   You may need to re-encrypt data files with the rolled-back key.")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m core.key_rotation <rotate|verify|rollback>")
        sys.exit(1)

    command = sys.argv[1].lower()
    if command == "rotate":
        success = rotate()
    elif command == "verify":
        success = verify()
    elif command == "rollback":
        success = rollback()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python -m core.key_rotation <rotate|verify|rollback>")
        sys.exit(1)

    sys.exit(0 if success else 1)
