"""
XIOPATH — Session Router
===========================
Manages workflow execution sessions: list, detail, cancel, and re-run.
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from api.routers.auth import get_current_user
from sqlalchemy import text
import logging

router = APIRouter(prefix="/sessions", tags=["Sessions"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_sessions(
    request: Request,
    user: dict = Depends(get_current_user),
    status: str = None,
    limit: int = 50,
    offset: int = 0,
):
    """
    List workflow execution sessions for the authenticated user.
    Optional status filter: completed, failed, running, queued.
    """
    db = request.app.state.db
    try:
        with db.SessionLocal() as session:
            query = "SELECT * FROM sessions WHERE user_id = :uid"
            params = {"uid": user.get("sub")}

            if status:
                query += " AND status = :status"
                params["status"] = status

            query += " ORDER BY started_at DESC LIMIT :limit OFFSET :offset"
            params["limit"] = limit
            params["offset"] = offset

            rows = session.execute(text(query), params).fetchall()

            sessions_list = []
            for row in rows:
                sessions_list.append({
                    "id": row.id,
                    "intent": row.intent,
                    "url": row.url,
                    "status": row.status,
                    "steps": getattr(row, 'steps', 0),
                    "duration": getattr(row, 'duration', None),
                    "error": getattr(row, 'error', None),
                    "started_at": str(row.started_at) if hasattr(row, 'started_at') else None,
                    "finished_at": str(row.finished_at) if hasattr(row, 'finished_at') else None,
                })

            return {"sessions": sessions_list, "total": len(sessions_list)}
    except Exception as e:
        logger.warning(f"Sessions table may not exist yet: {e}")
        return {"sessions": [], "total": 0}


@router.get("/{session_id}")
async def get_session_detail(
    session_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Get detailed information about a specific session."""
    db = request.app.state.db
    try:
        with db.SessionLocal() as session:
            row = session.execute(
                text("SELECT * FROM sessions WHERE id = :sid AND user_id = :uid"),
                {"sid": session_id, "uid": user.get("sub")}
            ).fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Session not found")

            return {
                "id": row.id,
                "intent": row.intent,
                "url": row.url,
                "status": row.status,
                "steps": getattr(row, 'steps', 0),
                "duration": getattr(row, 'duration', None),
                "error": getattr(row, 'error', None),
                "started_at": str(row.started_at) if hasattr(row, 'started_at') else None,
                "finished_at": str(row.finished_at) if hasattr(row, 'finished_at') else None,
                "log": getattr(row, 'execution_log', []),
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}/cancel")
async def cancel_session(
    session_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Cancel a running session."""
    db = request.app.state.db
    try:
        with db.safe_transaction() as session:
            result = session.execute(
                text("UPDATE sessions SET status = 'cancelled' WHERE id = :sid AND user_id = :uid AND status = 'running'"),
                {"sid": session_id, "uid": user.get("sub")}
            )

            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="No running session found with that ID")

            return {"status": "success", "message": f"Session {session_id} cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
