"""
XIOPATH — Vault Router
========================
Secure credential management with full CRUD and auth middleware.
All endpoints require JWT authentication.
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from api.routers.auth import get_current_user, require_admin
import logging

router = APIRouter(prefix="/vault", tags=["Vault"])
logger = logging.getLogger(__name__)


class SecretAddRequest(BaseModel):
    key: str
    value: str


class SecretUpdateRequest(BaseModel):
    value: str


@router.get("/keys")
async def get_keys(request: Request, user: dict = Depends(get_current_user)):
    """Returns a list of all secret keys. Requires authentication."""
    try:
        secret_manager = request.app.state.secret_manager
        keys = secret_manager.list_keys()
        return {"keys": keys, "count": len(keys)}
    except Exception as e:
        logger.error(f"Failed to list vault keys: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add")
async def add_secret(req: SecretAddRequest, request: Request, user: dict = Depends(get_current_user)):
    """Adds a new secret to the vault. Requires authentication."""
    try:
        secret_manager = request.app.state.secret_manager
        # Check if key already exists
        existing_keys = secret_manager.list_keys()
        if req.key in existing_keys:
            raise HTTPException(status_code=409, detail=f"Secret '{req.key}' already exists. Use PUT to update.")

        secret_manager.set_secret(req.key, req.value)
        logger.info(f"Vault: Secret '{req.key}' added by user {user.get('sub')}")
        return {"status": "success", "message": f"Secret '{req.key}' added successfully."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add secret: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{key}")
async def update_secret(key: str, req: SecretUpdateRequest, request: Request, user: dict = Depends(get_current_user)):
    """Updates an existing secret in the vault. Requires authentication."""
    try:
        secret_manager = request.app.state.secret_manager
        existing_keys = secret_manager.list_keys()
        if key not in existing_keys:
            raise HTTPException(status_code=404, detail=f"Secret '{key}' not found.")

        secret_manager.set_secret(key, req.value)
        logger.info(f"Vault: Secret '{key}' updated by user {user.get('sub')}")
        return {"status": "success", "message": f"Secret '{key}' updated successfully."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update secret: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{key}")
async def delete_secret(key: str, request: Request, user: dict = Depends(get_current_user)):
    """Deletes a secret from the vault. Requires authentication."""
    try:
        secret_manager = request.app.state.secret_manager
        existing_keys = secret_manager.list_keys()
        if key not in existing_keys:
            raise HTTPException(status_code=404, detail=f"Secret '{key}' not found.")

        # SecretManager uses a JSON file; we need to remove the key
        secret_manager.delete_secret(key)
        logger.info(f"Vault: Secret '{key}' deleted by user {user.get('sub')}")
        return {"status": "success", "message": f"Secret '{key}' deleted successfully."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete secret: {e}")
        raise HTTPException(status_code=500, detail=str(e))
