"""
XIOPATH — Phantom Tools Seed
==============================
Idempotent registration of phantom pipeline components as Tools
in the Universal Agent Ontology tool_registry.

Run this once (or on every startup — it's idempotent) to ensure
all phantom tools are visible in the ontology graph.

Educational purpose only.
"""

import logging
from typing import Dict

from core.ontology_ops import OntologyManager
from phantom.ontology_bridge import PhantomOntologyBridge

logger = logging.getLogger("phantom.tools_seed")


def seed_phantom_tools(ontology: OntologyManager) -> Dict[str, str]:
    """
    Register all phantom tools in the ontology. Idempotent.

    Args:
        ontology: An initialized OntologyManager instance.

    Returns:
        Dict mapping tool names to their ontology IDs.

    Usage::

        from core.database import DatabaseManager
        from core.ontology_ops import OntologyManager
        from phantom.tools_seed import seed_phantom_tools

        db = DatabaseManager()
        ontology = OntologyManager(db)
        tool_ids = seed_phantom_tools(ontology)
        print(tool_ids)
        # {'IdentityForge': '019f...', 'SanitizationPipeline': '019f...', ...}
    """
    bridge = PhantomOntologyBridge(ontology)
    tool_ids = bridge.register_phantom_tools()

    logger.info(f"Phantom tools seeded: {len(tool_ids)} tools registered")
    for name, tid in tool_ids.items():
        logger.info(f"  └─ {name}: {tid}")

    return tool_ids


def seed_all(ontology: OntologyManager) -> Dict[str, any]:
    """
    Full phantom seed: tools + verify Phantom Mesh agent exists.

    Returns:
        Dict with 'tools' and 'phantom_mesh_id'.
    """
    bridge = PhantomOntologyBridge(ontology)

    # Ensure Phantom Mesh ecosystem agent exists (created by ontology seed)
    mesh_id = bridge.phantom_mesh_id
    if not mesh_id:
        logger.warning(
            "Phantom Mesh ecosystem agent not found. "
            "Run ontology_ops.seed_initial_agents() first."
        )

    # Register tools
    tool_ids = bridge.register_phantom_tools()

    return {
        "tools": tool_ids,
        "phantom_mesh_id": mesh_id,
    }
