import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


DEFAULT_WORKSPACE_ID = "default"


class Workspace(Base):
    """A tenant boundary -- one production/event/team's incidents and users.

    `id` is a short slug (e.g. "default") rather than a UUID since it's
    meant to be readable in a workspace switcher / query param, not opaque.
    """

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # viewer < operator < admin -- see app/auth.py for the hierarchy this
    # gates against. admin ignores workspace_id (sees/acts on every
    # workspace); viewer/operator are scoped to exactly one.
    role: Mapped[str] = mapped_column(String(16), default="viewer")
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), default=DEFAULT_WORKSPACE_ID)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLogRow(Base):
    """One row per sensitive action -- who did what, to what, and when.
    Written by app/auth.py's record_audit() helper from the routers that
    take an authenticated action (login, approve/reject, inject-anomaly,
    user management). See docs/security.md.
    """

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_email: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# Incidents, agent events, remediation actions, postmortems, and token usage
# -- the UI-facing, agent-written timeline data -- live in Firestore
# instead of here. See app/firestore_db.py and app/services/incident_store.py.
