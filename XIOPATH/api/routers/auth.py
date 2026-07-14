"""
XIOPATH — Authentication Router (v5.0)
========================================
Handles user signup, login, and JWT token management.

v5.0 changes:
  - Queries `auth_identities` table (falls back to legacy `users` table)
  - JWT payload includes `actor_id` linking to the ontology
  - Signup creates both an `auth_identity` and a corresponding `actor`
  - Login tracking (last_login_at, login_count)
  - Account lockout support (failed_attempts, locked_until)
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, ConfigDict, field_validator
import jwt
import uuid
import datetime
import bcrypt
import os
import logging
from sqlalchemy import text

from core.tenant_context import TenantContext

router = APIRouter()
logger = logging.getLogger("Auth")

# ─── Security: Load secret from environment ──────────────────
SECRET_KEY = os.environ.get("XIOPATH_JWT_SECRET", "xiopath-dev-secret-change-in-production")
# C9 Fix: Fail hard on default secrets in production
if SECRET_KEY == "xiopath-dev-secret-change-in-production" and os.environ.get("XIOPATH_ENV") == "production":
    raise RuntimeError("CRITICAL: XIOPATH_JWT_SECRET must be set in production. Refusing to start with default secret.")
ALGORITHM = "HS256"
TOKEN_EXPIRY_MINUTES = 60
TOKEN_ISSUER = "xiopath-api"
TOKEN_AUDIENCE = "xiopath-web"

# Account lockout config
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _uuid7() -> str:
    try:
        return str(uuid.uuid7())
    except AttributeError:
        return str(uuid.uuid4())


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def _build_access_token(*, subject: str, role: str, username: str | None = None,
                        auth_id: str | None = None) -> str:
    """Issue a short-lived access token with a verifiable identity contract."""
    now = _utcnow()
    payload = {
        "sub": subject,
        "role": role,
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + datetime.timedelta(minutes=TOKEN_EXPIRY_MINUTES),
        "jti": str(uuid.uuid4()),
    }
    if username:
        payload["username"] = username
    if auth_id:
        payload["auth_id"] = auth_id
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _has_table(session, table_name: str) -> bool:
    """Check if a table exists (SQLite-compatible)."""
    try:
        session.execute(text(f"SELECT 1 FROM {table_name} LIMIT 0"))
        return True
    except Exception:
        return False


class CredentialsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str

    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        v = v.strip()
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        if len(v) > 50:
            raise ValueError('Username must be at most 50 characters')
        if not v.isalnum() and '_' not in v:
            raise ValueError('Username can only contain letters, numbers, and underscores')
        return v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if len(v) > 128:
            raise ValueError('Password must be at most 128 characters')
        return v


class SignupRequest(CredentialsRequest):
    """Public registration input. Roles are always assigned server-side."""


class LoginRequest(CredentialsRequest):
    """Authentication input. Authorization claims are never client supplied."""


# ═════════════════════════════════════════════════════════════════════════════
# SIGNUP
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/signup")
async def signup(req: SignupRequest, request: Request):
    """Create a new user account with password hashing."""
    db = request.app.state.db
    now = _utcnow()

    with db.safe_transaction() as session:
        use_v5 = _has_table(session, "auth_identities")

        if use_v5:
            # v5.0: Check auth_identities
            existing = session.execute(
                text("SELECT id FROM auth_identities WHERE username = :u"),
                {"u": req.username}
            ).fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="Username already exists")

            # Create actor (human entity)
            actor_id = _uuid7()
            session.execute(
                text("""INSERT INTO actors (id, actor_type, actor_subtype, role, alias,
                        state, lifecycle_phase, trust_tier, created_at, created_by)
                        VALUES (:id, 'human', :subtype, :role, :alias,
                        'active', 'operational', 'standard', :now, 'signup')"""),
                {
                    "id": actor_id,
                    "subtype": "member",
                    "role": "client",
                    "alias": req.username,
                    "now": now.isoformat(),
                }
            )

            # Create auth_identity
            auth_id = _uuid7()
            password_hash = bcrypt.hashpw(
                req.password.encode('utf-8'), bcrypt.gensalt()
            ).decode('utf-8')

            session.execute(
                text("""INSERT INTO auth_identities
                        (id, actor_id, username, auth_method, auth_credential, auth_role,
                         state, login_count, failed_attempts, created_at)
                        VALUES (:id, :actor_id, :username, 'password', :credential,
                         :role, 'active', 0, 0, :now)"""),
                {
                    "id": auth_id,
                    "actor_id": actor_id,
                    "username": req.username,
                    "credential": password_hash,
                    "role": "client",
                    "now": now.isoformat(),
                }
            )

            return {
                "status": "success",
                "message": "Account created successfully",
                "actor_id": actor_id,
            }

        else:
            # Legacy: use users table
            existing = session.execute(
                text("SELECT id FROM users WHERE username = :u"),
                {"u": req.username}
            ).fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="Username already exists")

            user_id = str(uuid.uuid4())
            password_hash = bcrypt.hashpw(
                req.password.encode('utf-8'), bcrypt.gensalt()
            ).decode('utf-8')

            session.execute(
                text("INSERT INTO users (id, username, password_hash, role) VALUES (:id, :u, :p, :r)"),
                {"id": user_id, "u": req.username, "p": password_hash, "r": "client"}
            )
            return {"status": "success", "message": "User created successfully"}


# ═════════════════════════════════════════════════════════════════════════════
# LOGIN
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/login")
async def login(req: LoginRequest, request: Request):
    """Authenticate user and return JWT token."""
    db = request.app.state.db
    now = _utcnow()

    with db.SessionLocal() as session:
        use_v5 = _has_table(session, "auth_identities")

        if use_v5:
            # v5.0: Query auth_identities
            identity = session.execute(
                text("SELECT * FROM auth_identities WHERE username = :u AND state = 'active'"),
                {"u": req.username}
            ).mappings().first()

            if not identity:
                raise HTTPException(status_code=401, detail="Invalid credentials")

            # Check account lockout
            locked_until = identity.get("locked_until")
            if locked_until:
                lock_time = datetime.datetime.fromisoformat(str(locked_until))
                if now < lock_time:
                    remaining = int((lock_time - now).total_seconds() / 60) + 1
                    raise HTTPException(
                        status_code=423,
                        detail=f"Account locked. Try again in {remaining} minute(s)."
                    )

            # Verify password
            if not bcrypt.checkpw(req.password.encode('utf-8'), identity["auth_credential"].encode('utf-8')):
                # Increment failed attempts
                failed = (identity.get("failed_attempts") or 0) + 1
                updates = {"failed": failed, "id": identity["id"]}

                if failed >= MAX_FAILED_ATTEMPTS:
                    lock_until = now + datetime.timedelta(minutes=LOCKOUT_MINUTES)
                    session.execute(
                        text("""UPDATE auth_identities
                                SET failed_attempts = :failed, locked_until = :lock
                                WHERE id = :id"""),
                        {**updates, "lock": lock_until.isoformat()}
                    )
                    session.commit()
                    raise HTTPException(
                        status_code=423,
                        detail=f"Account locked for {LOCKOUT_MINUTES} minutes after {MAX_FAILED_ATTEMPTS} failed attempts."
                    )
                else:
                    session.execute(
                        text("UPDATE auth_identities SET failed_attempts = :failed WHERE id = :id"),
                        updates
                    )
                    session.commit()

                raise HTTPException(status_code=401, detail="Invalid credentials")

            # Successful login — reset counters, update tracking
            session.execute(
                text("""UPDATE auth_identities
                        SET last_login_at = :now, login_count = login_count + 1,
                            failed_attempts = 0, locked_until = NULL
                        WHERE id = :id"""),
                {"now": now.isoformat(), "id": identity["id"]}
            )
            session.commit()

            token = _build_access_token(
                subject=identity["actor_id"],
                auth_id=identity["id"],
                role=identity["auth_role"],
                username=identity["username"],
            )

            return {
                "status": "success",
                "token": token,
                "role": identity["auth_role"],
                "username": identity["username"],
                "actor_id": identity["actor_id"],
                "sub": identity["actor_id"],
            }

        else:
            # Legacy: use users table
            user = session.execute(
                text("SELECT * FROM users WHERE username = :u"),
                {"u": req.username}
            ).fetchone()

            if not user or not bcrypt.checkpw(req.password.encode('utf-8'), user.password_hash.encode('utf-8')):
                raise HTTPException(status_code=401, detail="Invalid credentials")

            payload = {
                "sub": user.id,
                "role": user.role,
                "exp": now + datetime.timedelta(days=TOKEN_EXPIRY_DAYS)
            }
            token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

            return {
                "status": "success",
                "token": token,
                "role": user.role,
                "username": user.username,
                "sub": user.id,
            }


# ═════════════════════════════════════════════════════════════════════════════
# CURRENT USER
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/me")
async def get_current_user_info(request: Request, user: dict = Depends(lambda request: get_current_user(request))):
    """Return the current authenticated user's info."""
    return {
        "actor_id": user.get("sub"),
        "role": user.get("role"),
        "username": user.get("username"),
    }


# ═════════════════════════════════════════════════════════════════════════════
# AUTH DEPENDENCIES (used by other routers)
# ═════════════════════════════════════════════════════════════════════════════

def get_current_user(request: Request):
    """Extract and validate JWT token from Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# C6 Fix: Admin-only dependency (was referenced but never defined)
def require_admin(request: Request):
    """Dependency that requires the user to have admin role."""
    user = get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


def require_worker_or_admin(request: Request):
    """Dependency that allows both admin and worker roles (for self-registration etc.)."""
    user = get_current_user(request)
    if user.get("role") not in ("admin", "worker"):
        raise HTTPException(status_code=403, detail="Admin or worker privileges required")
    return user
