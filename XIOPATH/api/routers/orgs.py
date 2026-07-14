"""
XIOPATH — API v2: Organizations Router
==========================================
Multi-tenant organization management.

POST   /orgs                       — Create organization
GET    /orgs                       — List user's organizations
GET    /orgs/{org_id}              — Get org details
PATCH  /orgs/{org_id}              — Update org settings (owner/admin)
DELETE /orgs/{org_id}              — Archive org (owner only)

POST   /orgs/{org_id}/members      — Invite member
GET    /orgs/{org_id}/members      — List members
PATCH  /orgs/{org_id}/members/{actor_id}  — Update member role
DELETE /orgs/{org_id}/members/{actor_id}  — Remove member
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
import json
import logging
import uuid
import datetime
from sqlalchemy import text

from api.routers.auth import get_current_user, require_admin

router = APIRouter(prefix="/orgs", tags=["Organizations v2"])
logger = logging.getLogger(__name__)


def _uuid7() -> str:
    try:
        return str(uuid.uuid7())
    except AttributeError:
        return str(uuid.uuid4())


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ─── Request/Response Models ─────────────────────────────────────────────────

class CreateOrgRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    display_name: Optional[str] = None
    plan: str = Field("free", pattern="^(free|pro|enterprise)$")
    billing_email: Optional[str] = None
    metadata: Optional[dict] = None


class UpdateOrgRequest(BaseModel):
    display_name: Optional[str] = None
    plan: Optional[str] = None
    billing_email: Optional[str] = None
    state: Optional[str] = None
    metadata: Optional[dict] = None


class InviteMemberRequest(BaseModel):
    actor_id: str = Field(..., description="Actor ID to invite")
    role: str = Field("member", pattern="^(owner|admin|member|viewer)$")


class UpdateMemberRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(owner|admin|member|viewer)$")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_db(request: Request):
    return request.app.state.db


def _get_membership(session, org_id: str, actor_id: str):
    """Get a user's membership in an org."""
    row = session.execute(
        text("SELECT * FROM org_memberships WHERE org_id = :org_id AND actor_id = :actor_id AND state = 'active'"),
        {"org_id": org_id, "actor_id": actor_id}
    ).mappings().first()
    return dict(row) if row else None


def _require_org_role(session, org_id: str, actor_id: str, required_roles: list):
    """Check the user has the required role in the org."""
    membership = _get_membership(session, org_id, actor_id)
    if not membership or membership["role"] not in required_roles:
        raise HTTPException(403, f"Requires one of roles: {required_roles} in this organization")
    return membership


# ═════════════════════════════════════════════════════════════════════════════
# ORGANIZATION CRUD
# ═════════════════════════════════════════════════════════════════════════════

@router.post("")
async def create_org(
    req: CreateOrgRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Create a new organization. The creator becomes the owner."""
    db = _get_db(request)
    now = _utcnow()
    org_id = _uuid7()
    actor_id = user.get("sub")
    slug = req.name.lower().replace(" ", "-").replace("_", "-")

    with db.safe_transaction() as session:
        # Check name uniqueness
        existing = session.execute(
            text("SELECT id FROM organizations WHERE name = :name OR slug = :slug"),
            {"name": req.name, "slug": slug}
        ).fetchone()
        if existing:
            raise HTTPException(400, "Organization name already taken")

        # Create org
        session.execute(
            text("""INSERT INTO organizations
                    (id, name, display_name, slug, plan, state, owner_actor_id,
                     billing_email, created_at, metadata)
                    VALUES (:id, :name, :display_name, :slug, :plan, 'active', :owner,
                     :billing_email, :now, :metadata)"""),
            {
                "id": org_id,
                "name": req.name,
                "display_name": req.display_name or req.name,
                "slug": slug,
                "plan": req.plan,
                "owner": actor_id,
                "billing_email": req.billing_email,
                "now": now,
                "metadata": json.dumps(req.metadata) if req.metadata else None,
            }
        )

        # Create owner membership
        session.execute(
            text("""INSERT INTO org_memberships
                    (id, org_id, actor_id, role, state, joined_at, created_at)
                    VALUES (:id, :org_id, :actor_id, 'owner', 'active', :now, :now)"""),
            {"id": _uuid7(), "org_id": org_id, "actor_id": actor_id, "now": now}
        )

    return {"status": "success", "org_id": org_id, "slug": slug}


@router.get("")
async def list_orgs(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """List organizations the current user belongs to."""
    db = _get_db(request)
    actor_id = user.get("sub")

    with db.SessionLocal() as session:
        rows = session.execute(
            text("""SELECT o.*, m.role as member_role
                    FROM organizations o
                    JOIN org_memberships m ON o.id = m.org_id
                    WHERE m.actor_id = :actor_id AND m.state = 'active' AND o.state != 'archived'
                    ORDER BY o.name"""),
            {"actor_id": actor_id}
        ).mappings().all()

    return {
        "organizations": [dict(r) for r in rows],
        "total": len(rows),
    }


@router.get("/{org_id}")
async def get_org(
    org_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Get organization details."""
    db = _get_db(request)

    with db.SessionLocal() as session:
        org = session.execute(
            text("SELECT * FROM organizations WHERE id = :id"),
            {"id": org_id}
        ).mappings().first()
        if not org:
            raise HTTPException(404, "Organization not found")

        # Check membership
        membership = _get_membership(session, org_id, user.get("sub"))
        if not membership and user.get("role") != "admin":
            raise HTTPException(403, "Not a member of this organization")

        members_count = session.execute(
            text("SELECT COUNT(*) FROM org_memberships WHERE org_id = :org_id AND state = 'active'"),
            {"org_id": org_id}
        ).scalar()

    result = dict(org)
    result["members_count"] = members_count
    result["your_role"] = membership["role"] if membership else "system_admin"
    return result


@router.patch("/{org_id}")
async def update_org(
    org_id: str,
    req: UpdateOrgRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Update organization settings (owner/admin only)."""
    db = _get_db(request)
    now = _utcnow()

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")

    if "metadata" in updates:
        updates["metadata"] = json.dumps(updates["metadata"])

    with db.safe_transaction() as session:
        _require_org_role(session, org_id, user.get("sub"), ["owner", "admin"])

        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["org_id"] = org_id
        updates["now"] = now

        session.execute(
            text(f"UPDATE organizations SET {set_clause}, updated_at = :now WHERE id = :org_id"),
            updates
        )

    return {"status": "success", "updated_fields": list(req.model_dump(exclude_none=True).keys())}


@router.delete("/{org_id}")
async def archive_org(
    org_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Archive an organization (owner only)."""
    db = _get_db(request)

    with db.safe_transaction() as session:
        _require_org_role(session, org_id, user.get("sub"), ["owner"])

        session.execute(
            text("UPDATE organizations SET state = 'archived', updated_at = :now WHERE id = :id"),
            {"id": org_id, "now": _utcnow()}
        )

    return {"status": "success", "action": "archived"}


# ═════════════════════════════════════════════════════════════════════════════
# MEMBER MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/{org_id}/members")
async def invite_member(
    org_id: str,
    req: InviteMemberRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Invite an actor to the organization (admin/owner only)."""
    db = _get_db(request)
    now = _utcnow()

    with db.safe_transaction() as session:
        _require_org_role(session, org_id, user.get("sub"), ["owner", "admin"])

        # Check actor exists
        actor = session.execute(
            text("SELECT id FROM actors WHERE id = :id"),
            {"id": req.actor_id}
        ).fetchone()
        if not actor:
            raise HTTPException(404, "Actor not found")

        # Check not already a member
        existing = _get_membership(session, org_id, req.actor_id)
        if existing:
            raise HTTPException(409, "Actor is already a member")

        membership_id = _uuid7()
        session.execute(
            text("""INSERT INTO org_memberships
                    (id, org_id, actor_id, role, state, invited_by, joined_at, created_at)
                    VALUES (:id, :org_id, :actor_id, :role, 'active', :invited_by, :now, :now)"""),
            {
                "id": membership_id,
                "org_id": org_id,
                "actor_id": req.actor_id,
                "role": req.role,
                "invited_by": user.get("sub"),
                "now": now,
            }
        )

    return {"status": "success", "membership_id": membership_id}


@router.get("/{org_id}/members")
async def list_members(
    org_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """List organization members."""
    db = _get_db(request)

    with db.SessionLocal() as session:
        # Verify caller is a member
        membership = _get_membership(session, org_id, user.get("sub"))
        if not membership and user.get("role") != "admin":
            raise HTTPException(403, "Not a member of this organization")

        rows = session.execute(
            text("""SELECT m.*, a.alias as actor_name, a.actor_type, a.actor_subtype
                    FROM org_memberships m
                    LEFT JOIN actors a ON m.actor_id = a.id
                    WHERE m.org_id = :org_id AND m.state = 'active'
                    ORDER BY m.role, a.alias"""),
            {"org_id": org_id}
        ).mappings().all()

    return {"members": [dict(r) for r in rows], "total": len(rows)}


@router.patch("/{org_id}/members/{actor_id}")
async def update_member_role(
    org_id: str,
    actor_id: str,
    req: UpdateMemberRoleRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Update a member's role (owner only)."""
    db = _get_db(request)

    with db.safe_transaction() as session:
        _require_org_role(session, org_id, user.get("sub"), ["owner"])

        membership = _get_membership(session, org_id, actor_id)
        if not membership:
            raise HTTPException(404, "Member not found")

        session.execute(
            text("UPDATE org_memberships SET role = :role WHERE org_id = :org_id AND actor_id = :actor_id"),
            {"role": req.role, "org_id": org_id, "actor_id": actor_id}
        )

    return {"status": "success", "new_role": req.role}


@router.delete("/{org_id}/members/{actor_id}")
async def remove_member(
    org_id: str,
    actor_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Remove a member from the organization (admin/owner, or self-removal)."""
    db = _get_db(request)
    caller_id = user.get("sub")

    with db.safe_transaction() as session:
        # Self-removal allowed, otherwise need admin/owner
        if caller_id != actor_id:
            _require_org_role(session, org_id, caller_id, ["owner", "admin"])

        membership = _get_membership(session, org_id, actor_id)
        if not membership:
            raise HTTPException(404, "Member not found")

        # Prevent owner self-removal (must transfer ownership first)
        if membership["role"] == "owner" and caller_id == actor_id:
            raise HTTPException(400, "Owners cannot remove themselves. Transfer ownership first.")

        session.execute(
            text("UPDATE org_memberships SET state = 'removed' WHERE org_id = :org_id AND actor_id = :actor_id"),
            {"org_id": org_id, "actor_id": actor_id}
        )

    return {"status": "success", "action": "removed"}
