"""
XIOPATH — Marketplace API (Phase M.2 + P.8)
==========================================
REST endpoints for publishing, browsing, searching, installing,
and managing marketplace items (workflows, knowledge, bundles, environments).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from api.routers.auth import get_current_user

router = APIRouter(prefix="/marketplace", tags=["Marketplace"])
logger = logging.getLogger(__name__)


# ── Request/Response Models ────────────────────────────────────────────

class PublishRequest(BaseModel):
    environment_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    category: str = Field(default="automation", pattern=r"^(automation|scraping|testing|data-extraction|utility)$")
    tags: Optional[List[str]] = Field(default=None, max_length=10)


class PublishEntityRequest(BaseModel):
    """Universal publish request for any entity type."""
    entity_type: str = Field(..., pattern=r"^(workflow|knowledge|bundle|environment)$")
    entity_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    category: str = Field(default="automation")
    tags: Optional[List[str]] = None
    version: str = "1.0.0"
    license: str = "MIT"
    dependencies: Optional[List[str]] = None


class ReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=1000)


# ── Helpers ────────────────────────────────────────────────────────────

def _uuid7() -> str:
    import uuid
    return str(uuid.uuid4())


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_db(request: Request):
    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return db


def _get_env_manager(request: Request):
    from core.environment_manager import EnvironmentManager
    db = _get_db(request)
    return EnvironmentManager(db)


# ── Endpoints ──────────────────────────────────────────────────────────

@router.post("/publish")
async def publish_environment(
    req: PublishRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Publish an environment to the marketplace."""
    from sqlalchemy import text
    db = _get_db(request)
    env_mgr = _get_env_manager(request)

    # Verify environment exists and belongs to user
    env = env_mgr.get_environment(req.environment_id)
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    if env.get("agent_id") != user["sub"]:
        raise HTTPException(status_code=403, detail="You can only publish your own environments")

    # Check if already listed
    with db.SessionLocal() as session:
        existing = session.execute(
            text("SELECT id FROM marketplace_listings WHERE environment_id = :eid"),
            {"eid": req.environment_id},
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Environment already published")

    listing_id = _uuid7()
    now = _utcnow()

    with db.safe_transaction() as session:
        session.execute(text("""
            INSERT INTO marketplace_listings
            (id, environment_id, title, description, category, tags,
             creator_id, published_at, state)
            VALUES (:id, :eid, :title, :desc, :cat, :tags,
                    :creator, :published, :state)
        """), {
            "id": listing_id,
            "eid": req.environment_id,
            "title": req.title,
            "desc": req.description or "",
            "cat": req.category,
            "tags": json.dumps(req.tags or []),
            "creator": user["sub"],
            "published": now,
            "state": "active",
        })

    # Update environment visibility
    env_mgr.update_environment(req.environment_id, visibility="marketplace", is_portable=True)

    logger.info(f"Published listing {listing_id} for env {req.environment_id}")
    return {
        "listing_id": listing_id,
        "environment_id": req.environment_id,
        "title": req.title,
        "status": "published",
    }


@router.post("/publish/entity")
async def publish_entity(
    req: PublishEntityRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Publish any entity type (workflow, knowledge, bundle) to the marketplace."""
    from sqlalchemy import text
    db = _get_db(request)

    # Verify entity exists
    table_map = {
        "workflow": "workflows",
        "knowledge": "knowledge_nodes",
        "bundle": "bundles",
        "environment": "bundles",
    }
    table = table_map.get(req.entity_type)
    if not table:
        raise HTTPException(400, f"Invalid entity_type: {req.entity_type}")

    with db.SessionLocal() as session:
        entity = session.execute(
            text(f"SELECT id FROM {table} WHERE id = :id"),
            {"id": req.entity_id}
        ).fetchone()
        if not entity:
            raise HTTPException(404, f"{req.entity_type} not found")

        # Check not already listed
        existing = session.execute(
            text("SELECT id FROM marketplace_listings WHERE entity_id = :eid AND entity_type = :etype"),
            {"eid": req.entity_id, "etype": req.entity_type}
        ).fetchone()
        if existing:
            raise HTTPException(409, f"{req.entity_type} already published")

    listing_id = _uuid7()
    now = _utcnow()

    with db.safe_transaction() as session:
        session.execute(text("""
            INSERT INTO marketplace_listings
            (id, entity_type, entity_id, title, description, category, tags,
             version, license, dependencies, creator_id, published_at, state, install_count, avg_rating)
            VALUES (:id, :etype, :eid, :title, :desc, :cat, :tags,
                    :version, :license, :deps, :creator, :published, 'active', 0, 0.0)
        """), {
            "id": listing_id,
            "etype": req.entity_type,
            "eid": req.entity_id,
            "title": req.title,
            "desc": req.description or "",
            "cat": req.category,
            "tags": json.dumps(req.tags or []),
            "version": req.version,
            "license": req.license,
            "deps": json.dumps(req.dependencies or []),
            "creator": user["sub"],
            "published": now,
        })

    logger.info(f"Published {req.entity_type} listing {listing_id}")
    return {
        "listing_id": listing_id,
        "entity_type": req.entity_type,
        "entity_id": req.entity_id,
        "title": req.title,
        "status": "published",
    }


@router.get("/browse")
async def browse_marketplace(
    request: Request,
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Browse available marketplace environments (paginated). No auth required for browsing."""
    from sqlalchemy import text
    db = _get_db(request)

    conditions = ["state = 'active'"]
    params = {"limit": limit, "offset": offset}

    if category:
        conditions.append("category = :category")
        params["category"] = category

    where = " AND ".join(conditions)

    with db.SessionLocal() as session:
        rows = session.execute(
            text(f"""
                SELECT * FROM marketplace_listings
                WHERE {where}
                ORDER BY install_count DESC, published_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).mappings().fetchall()

        # Get total count
        count_row = session.execute(
            text(f"SELECT COUNT(*) as cnt FROM marketplace_listings WHERE {where}"),
            params,
        ).first()
        total = count_row[0] if count_row else 0

    listings = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d.get("tags", "[]"))
        d["rating"] = round(d.get("rating_sum", 0) / max(d.get("review_count", 1), 1), 1)
        listings.append(d)

    return {"listings": listings, "total": total, "limit": limit, "offset": offset}


@router.get("/search")
async def search_marketplace(
    request: Request,
    q: str = Query(..., min_length=1, max_length=200),
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Search marketplace by keyword."""
    from sqlalchemy import text
    db = _get_db(request)

    conditions = ["state = 'active'", "(title LIKE :q OR description LIKE :q OR tags LIKE :q)"]
    params = {"q": f"%{q}%", "limit": limit}

    if category:
        conditions.append("category = :category")
        params["category"] = category

    where = " AND ".join(conditions)

    with db.SessionLocal() as session:
        rows = session.execute(
            text(f"""
                SELECT * FROM marketplace_listings
                WHERE {where}
                ORDER BY install_count DESC
                LIMIT :limit
            """),
            params,
        ).mappings().fetchall()

    listings = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d.get("tags", "[]"))
        d["rating"] = round(d.get("rating_sum", 0) / max(d.get("review_count", 1), 1), 1)
        listings.append(d)

    return {"listings": listings, "query": q, "count": len(listings)}


@router.get("/{listing_id}")
async def get_listing_detail(
    listing_id: str,
    request: Request,
):
    """Get details of a single marketplace listing."""
    from sqlalchemy import text
    db = _get_db(request)

    with db.SessionLocal() as session:
        row = session.execute(
            text("SELECT * FROM marketplace_listings WHERE id = :id"),
            {"id": listing_id},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Listing not found")

    d = dict(row)
    d["tags"] = json.loads(d.get("tags", "[]"))
    d["rating"] = round(d.get("rating_sum", 0) / max(d.get("review_count", 1), 1), 1)

    # Get reviews
    with db.SessionLocal() as session:
        reviews = session.execute(
            text("SELECT * FROM marketplace_reviews WHERE listing_id = :lid ORDER BY created_at DESC LIMIT 20"),
            {"lid": listing_id},
        ).mappings().fetchall()
    d["reviews"] = [dict(r) for r in reviews]

    return d


@router.post("/{listing_id}/install")
async def install_listing(
    listing_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Install a marketplace environment for the current user."""
    from sqlalchemy import text
    db = _get_db(request)
    env_mgr = _get_env_manager(request)

    # Get the listing
    with db.SessionLocal() as session:
        listing = session.execute(
            text("SELECT * FROM marketplace_listings WHERE id = :id AND state = 'active'"),
            {"id": listing_id},
        ).mappings().first()

    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found or not active")

    listing = dict(listing)
    source_env = env_mgr.get_environment(listing["environment_id"])
    if not source_env:
        raise HTTPException(status_code=404, detail="Source environment not found")

    # Create a copy for the installer
    new_env_id = env_mgr.create_environment(
        agent_id=user["sub"],
        environment_type=source_env.get("environment_type", "workflow_bundle"),
        manifest=json.loads(source_env.get("manifest", "{}")),
        visibility="private",
        compatible_runtimes=json.loads(source_env.get("compatible_runtimes", "[]")),
    )

    # Increment install count
    with db.safe_transaction() as session:
        session.execute(
            text("UPDATE marketplace_listings SET install_count = install_count + 1 WHERE id = :id"),
            {"id": listing_id},
        )

    logger.info(f"User {user['sub']} installed listing {listing_id} as env {new_env_id}")
    return {
        "status": "installed",
        "environment_id": new_env_id,
        "listing_id": listing_id,
        "title": listing["title"],
    }


@router.delete("/{listing_id}")
async def unpublish_listing(
    listing_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Unpublish (archive) a marketplace listing. Only creator or admin."""
    from sqlalchemy import text
    db = _get_db(request)

    with db.SessionLocal() as session:
        listing = session.execute(
            text("SELECT * FROM marketplace_listings WHERE id = :id"),
            {"id": listing_id},
        ).mappings().first()

    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    listing = dict(listing)
    if listing["creator_id"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Only the creator can unpublish")

    with db.safe_transaction() as session:
        session.execute(
            text("UPDATE marketplace_listings SET state = 'archived' WHERE id = :id"),
            {"id": listing_id},
        )

    return {"status": "archived", "listing_id": listing_id}


@router.get("/my/published")
async def my_published(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """List creator's published environments."""
    from sqlalchemy import text
    db = _get_db(request)

    with db.SessionLocal() as session:
        rows = session.execute(
            text("SELECT * FROM marketplace_listings WHERE creator_id = :uid ORDER BY published_at DESC"),
            {"uid": user["sub"]},
        ).mappings().fetchall()

    return {"listings": [dict(r) for r in rows], "count": len(rows)}


@router.get("/my/installed")
async def my_installed(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """List user's installed environments."""
    env_mgr = _get_env_manager(request)
    envs = env_mgr.list_environments(agent_id=user["sub"], visibility="private")
    return {"environments": envs, "count": len(envs)}


@router.post("/{listing_id}/review")
async def add_review(
    listing_id: str,
    req: ReviewRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Add or update a review for a marketplace listing."""
    from sqlalchemy import text
    db = _get_db(request)

    # Verify listing exists
    with db.SessionLocal() as session:
        listing = session.execute(
            text("SELECT id FROM marketplace_listings WHERE id = :id AND state = 'active'"),
            {"id": listing_id},
        ).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    review_id = _uuid7()
    now = _utcnow()

    with db.safe_transaction() as session:
        # Check existing review
        existing = session.execute(
            text("SELECT id, rating FROM marketplace_reviews WHERE listing_id = :lid AND reviewer_id = :uid"),
            {"lid": listing_id, "uid": user["sub"]},
        ).first()

        if existing:
            # Update existing review
            old_rating = existing[1]
            session.execute(
                text("UPDATE marketplace_reviews SET rating = :rating, comment = :comment WHERE id = :id"),
                {"rating": req.rating, "comment": req.comment, "id": existing[0]},
            )
            # Update listing rating_sum (subtract old, add new)
            session.execute(
                text("UPDATE marketplace_listings SET rating_sum = rating_sum - :old + :new WHERE id = :lid"),
                {"old": old_rating, "new": req.rating, "lid": listing_id},
            )
        else:
            # Insert new review
            session.execute(text("""
                INSERT INTO marketplace_reviews (id, listing_id, reviewer_id, rating, comment, created_at)
                VALUES (:id, :lid, :uid, :rating, :comment, :created)
            """), {
                "id": review_id,
                "lid": listing_id,
                "uid": user["sub"],
                "rating": req.rating,
                "comment": req.comment,
                "created": now,
            })
            # Update listing stats
            session.execute(
                text("UPDATE marketplace_listings SET rating_sum = rating_sum + :rating, review_count = review_count + 1 WHERE id = :lid"),
                {"rating": req.rating, "lid": listing_id},
            )

    return {"status": "reviewed", "listing_id": listing_id, "rating": req.rating}
