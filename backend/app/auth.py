"""Auth: password hashing, JWT issuance/verification, role hierarchy, and
the FastAPI dependencies that gate protected routes. See docs/security.md.

Role hierarchy is deliberately simple -- three tiers, checked by rank:
  viewer   -- read-only (the control room and history pages need no auth
              at all today; this tier exists for future read-gated routes)
  operator -- can approve/reject remediations, inject demo anomalies,
              trigger chaos
  admin    -- everything operator can, plus user management and seeing
              every workspace regardless of their own workspace_id

Bootstrapping: ensure_bootstrap_data() creates the default workspace and,
the first time the users table is empty, one admin account from
settings.admin_email/admin_password -- called from main.py's lifespan
after init_db().
"""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select

from app.config import get_settings
from app.db import session_scope
from app.models.db import DEFAULT_WORKSPACE_ID, AuditLogRow, User, Workspace

logger = logging.getLogger(__name__)

Role = Literal["viewer", "operator", "admin"]
_ROLE_RANK: dict[str, int] = {"viewer": 0, "operator": 1, "admin": 2}

_PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, digest_hex = password_hash.split("$", 1)
    except ValueError:
        return False
    expected = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return hmac.compare_digest(expected.hex(), digest_hex)


# --- JWT ---------------------------------------------------------------------

# Fallback secret for when JWT_SECRET isn't set: random per process start, so
# tokens just stop validating across a restart rather than the app either
# refusing to boot or (worse) shipping a fixed default secret in source.
_ephemeral_secret = secrets.token_urlsafe(32)


def _jwt_secret() -> str:
    return get_settings().jwt_secret or _ephemeral_secret


def create_access_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "workspace_id": user.workspace_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


@dataclass
class CurrentUser:
    id: str
    email: str
    role: str
    workspace_id: str


def _decode_token(token: str) -> CurrentUser:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid or expired token") from exc
    return CurrentUser(
        id=payload["sub"], email=payload["email"], role=payload["role"], workspace_id=payload["workspace_id"]
    )


async def get_current_user(request: Request) -> CurrentUser:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    return _decode_token(header[len("bearer ") :].strip())


def require_role(minimum: Role):
    """FastAPI dependency factory: 403s unless the caller's role rank is at
    least `minimum`'s. Use as `user: CurrentUser = Depends(require_role("operator"))`."""

    async def _dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if _ROLE_RANK.get(user.role, -1) < _ROLE_RANK[minimum]:
            raise HTTPException(403, f"Requires '{minimum}' role or higher (you have '{user.role}')")
        return user

    return _dependency


# --- bootstrap ----------------------------------------------------------------


async def ensure_bootstrap_data() -> None:
    """Create the default workspace and, if no users exist yet, one admin
    account -- called once from main.py's lifespan after init_db()."""
    settings = get_settings()
    async with session_scope() as db:
        if await db.get(Workspace, DEFAULT_WORKSPACE_ID) is None:
            db.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Default"))

        user_count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
        if user_count == 0:
            password = settings.admin_password
            if not password:
                password = secrets.token_urlsafe(12)
                logger.warning(
                    "No ADMIN_PASSWORD set -- generated one for %s: %s "
                    "(shown once in this log; sign in and rotate it via the admin API)",
                    settings.admin_email,
                    password,
                )
            db.add(
                User(
                    email=settings.admin_email,
                    password_hash=hash_password(password),
                    role="admin",
                    workspace_id=DEFAULT_WORKSPACE_ID,
                )
            )
        await db.commit()


async def record_audit(
    actor_email: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    detail: dict | None = None,
) -> None:
    async with session_scope() as db:
        db.add(
            AuditLogRow(
                actor_email=actor_email,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                detail_json=detail or {},
            )
        )
        await db.commit()
