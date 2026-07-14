"""
Migration utilities for the Locator Data Structure refactoring.

Provides backward-compatible helpers that read `bounding_box` from both
`face_value` (new canonical location) and `place_value` (legacy location),
plus a batch migration function for existing memory nodes.
"""
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


def get_bounding_box(node: dict) -> Optional[dict]:
    """Read bounding_box from face_value (new) or place_value (legacy).

    Provides seamless backward compatibility during migration. New code
    always stores bounding_box in face_value; old nodes may still have
    it in place_value.
    """
    fv = node.get("face_value", {})
    pv = node.get("place_value", {})
    return fv.get("bounding_box") or pv.get("bounding_box")


def get_axes_xpath(node: dict) -> List[dict]:
    """Extract axes_xpath list from place_value (returns empty list if absent)."""
    pv = node.get("place_value", {})
    axes = pv.get("axes_xpath", [])
    if isinstance(axes, list):
        return axes
    return []


def migrate_node_structure(node: dict) -> dict:
    """Migrate a single node to the new locator structure (idempotent).

    Moves:
      - bounding_box: place_value → face_value
    Preserves:
      - visual_base64: stays in place_value (used for OpenCV fallback locator)
      - axes_xpath: stays in place_value (structural address)
    """
    fv = node.get("face_value", {})
    pv = node.get("place_value", {})

    # Move bounding_box from place_value → face_value (if not already migrated)
    if "bounding_box" in pv and "bounding_box" not in fv:
        bbox = pv.pop("bounding_box")

        # Enrich with normalized coordinates if window dimensions are available
        win_w = bbox.get("windowWidth", 0)
        win_h = bbox.get("windowHeight", 0)
        if win_w > 0 and win_h > 0:
            bbox["nx"] = round(bbox.get("x", 0) / win_w, 6)
            bbox["ny"] = round(bbox.get("y", 0) / win_h, 6)
            bbox["nw"] = round(bbox.get("width", bbox.get("w", 0)) / win_w, 6)
            bbox["nh"] = round(bbox.get("height", bbox.get("h", 0)) / win_h, 6)

        fv["bounding_box"] = bbox
        node["face_value"] = fv
        node["place_value"] = pv

    return node


def batch_migrate(db, batch_size: int = 100) -> int:
    """Migrate all existing memory nodes to the new structure.

    Reads each node, applies migrate_node_structure(), and writes back
    only if changes were made. Returns total number of migrated nodes.

    Args:
        db: DatabaseManager instance
        batch_size: Not used for SQLite (processes all), but reserved for
                    future PostgreSQL pagination.
    """
    all_nodes = db.get_all_nodes()
    migrated = 0

    for node in all_nodes:
        pv = node.get("place_value", {})
        fv = node.get("face_value", {})

        if "bounding_box" in pv and "bounding_box" not in fv:
            node = migrate_node_structure(node)
            db.update_node_fields(
                node["id"],
                face_value=node["face_value"],
                place_value=node["place_value"]
            )
            migrated += 1

    if migrated:
        logger.info(f"Migration complete: {migrated}/{len(all_nodes)} nodes updated")
    else:
        logger.info("No nodes required migration")

    return migrated
