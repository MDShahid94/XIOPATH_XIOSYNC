"""
XIOPATH — Schedule Router
============================
CRUD for scheduled/recurring workflow executions.
Stores job definitions in the database; actual scheduling
is handled by a background scheduler service.
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, field_validator
from api.routers.auth import get_current_user
from sqlalchemy import text
import uuid
import datetime
import json
import logging

router = APIRouter(prefix="/schedule", tags=["Schedule"])
logger = logging.getLogger(__name__)


class ScheduleJobRequest(BaseModel):
    name: str
    url: str
    intent: str
    cron: str
    enabled: bool = True

    @field_validator('cron')
    @classmethod
    def validate_cron(cls, v):
        parts = v.strip().split()
        if len(parts) != 5:
            raise ValueError('Cron expression must have exactly 5 fields (minute hour day-of-month month day-of-week)')
        return v.strip()


@router.get("/jobs")
async def list_jobs(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """List all scheduled jobs for the authenticated user."""
    db = request.app.state.db
    try:
        with db.SessionLocal() as session:
            rows = session.execute(
                text("SELECT * FROM scheduled_jobs WHERE user_id = :uid ORDER BY created_at DESC"),
                {"uid": user.get("sub")}
            ).fetchall()

            jobs = []
            for row in rows:
                jobs.append({
                    "id": row.id,
                    "name": row.name,
                    "url": row.url,
                    "intent": row.intent,
                    "cron": row.cron,
                    "enabled": bool(row.enabled),
                    "last_run": str(row.last_run) if hasattr(row, 'last_run') and row.last_run else None,
                    "next_run": str(row.next_run) if hasattr(row, 'next_run') and row.next_run else None,
                    "run_count": getattr(row, 'run_count', 0),
                    "status": 'active' if row.enabled else 'paused',
                })

            return {"jobs": jobs, "total": len(jobs)}
    except Exception as e:
        logger.warning(f"Scheduled jobs table may not exist yet: {e}")
        return {"jobs": [], "total": 0}


@router.post("/jobs")
async def create_job(
    req: ScheduleJobRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Create a new scheduled job."""
    db = request.app.state.db
    job_id = str(uuid.uuid4())[:12]

    try:
        with db.safe_transaction() as session:
            session.execute(
                text("""
                    INSERT INTO scheduled_jobs (id, user_id, name, url, intent, cron, enabled, created_at, run_count)
                    VALUES (:id, :uid, :name, :url, :intent, :cron, :enabled, :created, 0)
                """),
                {
                    "id": job_id,
                    "uid": user.get("sub"),
                    "name": req.name,
                    "url": req.url,
                    "intent": req.intent,
                    "cron": req.cron,
                    "enabled": req.enabled,
                    "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            )

        logger.info(f"Schedule: Job '{req.name}' created by {user.get('sub')}")
        return {"status": "success", "id": job_id, "message": f"Job '{req.name}' created successfully."}
    except Exception as e:
        logger.error(f"Failed to create scheduled job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/jobs/{job_id}/toggle")
async def toggle_job(
    job_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Toggle a scheduled job's enabled state."""
    db = request.app.state.db
    try:
        with db.safe_transaction() as session:
            row = session.execute(
                text("SELECT enabled FROM scheduled_jobs WHERE id = :jid AND user_id = :uid"),
                {"jid": job_id, "uid": user.get("sub")}
            ).fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Job not found")

            new_state = not row.enabled
            session.execute(
                text("UPDATE scheduled_jobs SET enabled = :enabled WHERE id = :jid"),
                {"enabled": new_state, "jid": job_id}
            )

        return {"status": "success", "enabled": new_state}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Delete a scheduled job."""
    db = request.app.state.db
    try:
        with db.safe_transaction() as session:
            result = session.execute(
                text("DELETE FROM scheduled_jobs WHERE id = :jid AND user_id = :uid"),
                {"jid": job_id, "uid": user.get("sub")}
            )

            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Job not found")

        logger.info(f"Schedule: Job {job_id} deleted by {user.get('sub')}")
        return {"status": "success", "message": f"Job {job_id} deleted successfully."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
