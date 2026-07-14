"""
XIOPATH — Bundle Format (Phase M.1)
======================================
Defines the .xio-env portable environment bundle format.
Bundles are compressed, encrypted archives containing workflows,
tools, memory snapshots, and configuration.
"""

import json
import gzip
import hashlib
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BUNDLE_MAGIC = b"XIOENV01"
BUNDLE_VERSION = 1


@dataclass
class BundleComponent:
    """A single component within a bundle."""
    component_type: str   # "workflow_graph" | "memory_snapshot" | "tool_config" | "ai_context"
    name: str             # Human-readable name
    data: Any = None      # Serializable data (dict, list, string)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "component_type": self.component_type,
            "name": self.name,
            "data": self.data,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'BundleComponent':
        return cls(
            component_type=d["component_type"],
            name=d["name"],
            data=d.get("data"),
            metadata=d.get("metadata", {}),
        )


@dataclass
class BundleManifest:
    """Top-level manifest for a .xio-env bundle."""
    version: int = BUNDLE_VERSION
    creator_id: str = ""
    environment_type: str = "workflow_bundle"   # "workflow_bundle" | "tool_kit" | "runtime_sandbox"
    execution_mode: str = "marketplace"         # "minimal" | "full" | "marketplace"
    title: str = ""
    description: str = ""
    components: List[BundleComponent] = field(default_factory=list)
    workflow_vars: Dict[str, str] = field(default_factory=dict)  # vault:// refs preserved
    compatible_runtimes: List[str] = field(default_factory=lambda: ["compute.work_runtime"])
    required_vault_keys: List[str] = field(default_factory=list)
    checksum: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return {
            "version": self.version,
            "creator_id": self.creator_id,
            "environment_type": self.environment_type,
            "execution_mode": self.execution_mode,
            "title": self.title,
            "description": self.description,
            "components": [c.to_dict() for c in self.components],
            "workflow_vars": self.workflow_vars,
            "compatible_runtimes": self.compatible_runtimes,
            "required_vault_keys": self.required_vault_keys,
            "checksum": self.checksum,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'BundleManifest':
        return cls(
            version=d.get("version", BUNDLE_VERSION),
            creator_id=d.get("creator_id", ""),
            environment_type=d.get("environment_type", "workflow_bundle"),
            execution_mode=d.get("execution_mode", "marketplace"),
            title=d.get("title", ""),
            description=d.get("description", ""),
            components=[BundleComponent.from_dict(c) for c in d.get("components", [])],
            workflow_vars=d.get("workflow_vars", {}),
            compatible_runtimes=d.get("compatible_runtimes", []),
            required_vault_keys=d.get("required_vault_keys", []),
            checksum=d.get("checksum", ""),
            created_at=d.get("created_at", ""),
        )

    def compute_checksum(self) -> str:
        """Compute SHA-256 of the manifest content (excluding derived fields)."""
        d = self.to_dict()
        d.pop("checksum", None)
        d.pop("required_vault_keys", None)  # Derived field — excluded from checksum
        raw = json.dumps(d, sort_keys=True).encode("utf-8")
        self.checksum = hashlib.sha256(raw).hexdigest()
        return self.checksum

    def extract_vault_keys(self) -> List[str]:
        """Scan workflow_vars and components for vault:// references."""
        keys = set()
        for v in self.workflow_vars.values():
            if isinstance(v, str) and v.startswith("vault://"):
                keys.add(v.replace("vault://", "").strip())
        # Also scan component data for vault refs
        for comp in self.components:
            if isinstance(comp.data, dict):
                self._scan_dict_for_vault(comp.data, keys)
        self.required_vault_keys = sorted(keys)
        return self.required_vault_keys

    def _scan_dict_for_vault(self, d: Dict, keys: set):
        for v in d.values():
            if isinstance(v, str) and v.startswith("vault://"):
                keys.add(v.replace("vault://", "").strip())
            elif isinstance(v, dict):
                self._scan_dict_for_vault(v, keys)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        self._scan_dict_for_vault(item, keys)


def serialize_bundle(manifest: BundleManifest, encrypt_key: bytes = None) -> bytes:
    """
    Serialize a BundleManifest into a .xio-env bundle.
    
    Format: MAGIC(8) + VERSION(4) + GZIP(JSON(manifest))
    Optional: encrypt with Fernet if key provided.
    
    Returns raw bytes.
    """
    manifest.compute_checksum()
    manifest.extract_vault_keys()
    
    payload = json.dumps(manifest.to_dict(), sort_keys=True).encode("utf-8")
    compressed = gzip.compress(payload, compresslevel=6)
    
    if encrypt_key:
        try:
            from cryptography.fernet import Fernet
            f = Fernet(encrypt_key)
            compressed = f.encrypt(compressed)
        except ImportError:
            logger.warning("cryptography not installed — bundle NOT encrypted")
        except Exception as e:
            logger.warning(f"Encryption failed — bundle NOT encrypted: {e}")
    
    # Assemble: MAGIC + VERSION (4 bytes big-endian) + compressed data
    import struct
    header = BUNDLE_MAGIC + struct.pack(">I", BUNDLE_VERSION)
    return header + compressed


def deserialize_bundle(raw: bytes, decrypt_key: bytes = None) -> BundleManifest:
    """
    Deserialize a .xio-env bundle back into a BundleManifest.
    
    Raises ValueError if magic bytes don't match.
    """
    import struct
    
    if not raw.startswith(BUNDLE_MAGIC):
        raise ValueError("Invalid bundle: magic bytes mismatch (expected XIOENV01)")
    
    version = struct.unpack(">I", raw[8:12])[0]
    if version > BUNDLE_VERSION:
        raise ValueError(f"Unsupported bundle version: {version} (max supported: {BUNDLE_VERSION})")
    
    compressed = raw[12:]
    
    if decrypt_key:
        try:
            from cryptography.fernet import Fernet
            f = Fernet(decrypt_key)
            compressed = f.decrypt(compressed)
        except ImportError:
            logger.warning("cryptography not installed — assuming unencrypted bundle")
        except Exception as e:
            raise ValueError(f"Bundle decryption failed: {e}")
    
    payload = gzip.decompress(compressed)
    data = json.loads(payload.decode("utf-8"))
    
    manifest = BundleManifest.from_dict(data)
    
    # Verify checksum
    stored_checksum = manifest.checksum
    computed = manifest.compute_checksum()
    if stored_checksum and stored_checksum != computed:
        raise ValueError(f"Bundle checksum mismatch: expected {stored_checksum}, got {computed}")
    
    return manifest
