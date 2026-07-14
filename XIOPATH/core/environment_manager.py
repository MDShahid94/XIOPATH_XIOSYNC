"""
XIOPATH — Environment Manager (Phase M.1)
============================================
CRUD operations for portable workflow environments.
Manages create, serialize (export), restore (import), and lifecycle.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy import text

from core.bundle_format import (
    BundleManifest, BundleComponent, BUNDLE_VERSION,
    serialize_bundle, deserialize_bundle,
)
from core.tenant_context import remap_vault_references, extract_required_vault_keys

logger = logging.getLogger(__name__)


def _uuid7() -> str:
    """Generate a UUIDv7-like ID."""
    import uuid
    return str(uuid.uuid4())


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class EnvironmentManager:
    """
    Manages portable workflow environments:
    - CRUD on the bundles table
    - Bundle serialization (.xio-env format)
    - Bundle restoration with vault remapping
    """

    def __init__(self, db_manager, memory_manager=None, secret_manager=None):
        self.db = db_manager
        self.memory = memory_manager
        self.secrets = secret_manager

    # ─── CRUD ──────────────────────────────────────────────────────────────

    def create_environment(
        self,
        agent_id: str,
        environment_type: str = "workflow_bundle",
        manifest: Dict = None,
        visibility: str = "private",
        compatible_runtimes: List[str] = None,
    ) -> str:
        """Create a new environment record. Returns the env_id."""
        env_id = _uuid7()
        now = _utcnow()

        with self.db.SessionLocal() as session:
            session.execute(text("""
                INSERT INTO bundles
                (id, agent_id, environment_type, manifest, storage_backend,
                 storage_path, is_portable, visibility, compatible_runtimes,
                 created_at, version, state)
                VALUES (:id, :agent_id, :env_type, :manifest, :storage,
                        :path, :portable, :visibility, :runtimes,
                        :created, :version, :state)
            """), {
                "id": env_id,
                "agent_id": agent_id,
                "env_type": environment_type,
                "manifest": json.dumps(manifest or {}),
                "storage": "local",
                "path": f"environments/{env_id}.xio-env",
                "portable": visibility in ("shared", "marketplace"),
                "visibility": visibility,
                "runtimes": json.dumps(compatible_runtimes or ["compute.work_runtime"]),
                "created": now,
                "version": "1.0.0",
                "state": "active",
            })
            session.commit()

        logger.info(f"Environment created: {env_id} (type={environment_type}, vis={visibility})")
        return env_id

    def get_environment(self, env_id: str) -> Optional[Dict]:
        """Get a single environment by ID."""
        with self.db.SessionLocal() as session:
            row = session.execute(
                text("SELECT * FROM bundles WHERE id = :id"),
                {"id": env_id}
            ).mappings().first()
            return dict(row) if row else None

    def list_environments(
        self,
        agent_id: str = None,
        visibility: str = None,
        state: str = "active",
        limit: int = 50,
    ) -> List[Dict]:
        """List environments with optional filters."""
        conditions = ["state = :state"]
        params: Dict[str, Any] = {"state": state, "limit": limit}

        if agent_id:
            conditions.append("agent_id = :agent_id")
            params["agent_id"] = agent_id
        if visibility:
            conditions.append("visibility = :visibility")
            params["visibility"] = visibility

        where_clause = " AND ".join(conditions)
        with self.db.SessionLocal() as session:
            rows = session.execute(
                text(f"SELECT * FROM bundles WHERE {where_clause} ORDER BY created_at DESC LIMIT :limit"),
                params,
            ).mappings().fetchall()
            return [dict(r) for r in rows]

    def update_environment(self, env_id: str, **fields) -> bool:
        """Update environment fields."""
        if not fields:
            return False
        # Only allow safe fields
        allowed = {"manifest", "visibility", "state", "version", "is_portable",
                    "storage_backend", "storage_path", "bundle_checksum",
                    "bundle_size_bytes", "last_serialized_at"}
        safe_fields = {k: v for k, v in fields.items() if k in allowed}
        if not safe_fields:
            return False

        set_clause = ", ".join(f"{k} = :{k}" for k in safe_fields)
        safe_fields["id"] = env_id
        with self.db.SessionLocal() as session:
            result = session.execute(
                text(f"UPDATE bundles SET {set_clause} WHERE id = :id"),
                safe_fields,
            )
            session.commit()
            return result.rowcount > 0

    def delete_environment(self, env_id: str) -> bool:
        """Soft-delete: set state to 'archived'."""
        return self.update_environment(env_id, state="archived")

    # ─── BUNDLE SERIALIZATION ─────────────────────────────────────────────

    def build_manifest(
        self,
        env_id: str,
        title: str,
        description: str,
        creator_id: str,
        workflow_intent: str = None,
        workflow_url: str = None,
        workflow_vars: Dict = None,
        execution_mode: str = "marketplace",
    ) -> BundleManifest:
        """
        Build a BundleManifest from an environment's data.
        Collects the workflow graph, tool configs, and memory context.
        """
        env = self.get_environment(env_id)
        if not env:
            raise ValueError(f"Environment {env_id} not found")

        components = []

        # 1. Workflow graph (if intent provided)
        if workflow_intent and workflow_url and self.memory:
            graph = self.memory.get_workflow_graph(
                workflow_url, workflow_intent, {}, max_fallback_tier=2
            )
            if graph:
                components.append(BundleComponent(
                    component_type="workflow_graph",
                    name=workflow_intent,
                    data=graph,
                    metadata={"url": workflow_url, "intent": workflow_intent},
                ))

        # 2. Environment manifest from DB
        db_manifest = json.loads(env.get("manifest", "{}"))
        if db_manifest:
            components.append(BundleComponent(
                component_type="ai_context",
                name="environment_config",
                data=db_manifest,
                metadata={"source": "bundles"},
            ))

        manifest = BundleManifest(
            creator_id=creator_id,
            environment_type=env.get("environment_type", "workflow_bundle"),
            execution_mode=execution_mode,
            title=title,
            description=description,
            components=components,
            workflow_vars=workflow_vars or {},
            compatible_runtimes=json.loads(env.get("compatible_runtimes", "[]")),
        )
        manifest.extract_vault_keys()
        manifest.compute_checksum()

        return manifest

    def serialize_environment(self, env_id: str, manifest: BundleManifest) -> bytes:
        """
        Serialize an environment into a .xio-env bundle.
        Updates the DB record with checksum and size.
        """
        bundle_bytes = serialize_bundle(manifest)

        # Update DB with serialization metadata
        self.update_environment(
            env_id,
            bundle_checksum=manifest.checksum,
            bundle_size_bytes=len(bundle_bytes),
            last_serialized_at=_utcnow(),
        )

        logger.info(f"Serialized environment {env_id}: {len(bundle_bytes)} bytes, checksum={manifest.checksum[:16]}...")
        return bundle_bytes

    def restore_bundle(self, bundle_bytes: bytes, executor_id: str) -> Dict:
        """
        Restore a .xio-env bundle for execution by a specific user.
        
        Steps:
        1. Deserialize and validate
        2. Remap vault:// references to executor's namespace
        3. Create a new environment record (owned by executor)
        4. Return the manifest + env_id
        
        Returns:
            {"env_id": str, "manifest": BundleManifest, "required_vault_keys": [...]}
        """
        manifest = deserialize_bundle(bundle_bytes)

        # M.3: Remap vault references to executor's namespace
        remapped_vars = remap_vault_references(
            manifest.workflow_vars,
            f"vault_{executor_id}",
        )
        manifest.workflow_vars = remapped_vars

        # Extract required vault keys the executor needs
        required_keys = manifest.extract_vault_keys()

        # Create a new environment owned by the executor
        env_id = self.create_environment(
            agent_id=executor_id,
            environment_type=manifest.environment_type,
            manifest=manifest.to_dict(),
            visibility="private",
            compatible_runtimes=manifest.compatible_runtimes,
        )

        logger.info(f"Restored bundle for executor {executor_id}: env_id={env_id}, vault_keys={required_keys}")
        return {
            "env_id": env_id,
            "manifest": manifest,
            "required_vault_keys": required_keys,
        }
