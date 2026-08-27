import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="monitoring")
    grafana_incident_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), default=DEFAULT_WORKSPACE_ID)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    anomaly_events: Mapped[list["AnomalyEventRow"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    agent_events: Mapped[list["AgentEventRow"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    remediation_actions: Mapped[list["RemediationActionRow"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    postmortem: Mapped["PostmortemRow | None"] = relationship(
        back_populates="incident", cascade="all, delete-orphan", uselist=False
    )
    token_usage: Mapped[list["AgentTokenUsageRow"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )


class AnomalyEventRow(Base):
    __tablename__ = "anomaly_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    metric_name: Mapped[str] = mapped_column(String(128))
    observed_value: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    region: Mapped[str] = mapped_column(String(64))
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    incident: Mapped[Incident] = relationship(back_populates="anomaly_events")


class AgentEventRow(Base):
    __tablename__ = "agent_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    agent_name: Mapped[str] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    incident: Mapped[Incident] = relationship(back_populates="agent_events")


class RemediationActionRow(Base):
    __tablename__ = "remediation_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    action_type: Mapped[str] = mapped_column(String(64))
    risk_level: Mapped[str] = mapped_column(String(8))
    approval_status: Mapped[str] = mapped_column(String(16), default="not_required")
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    incident: Mapped[Incident] = relationship(back_populates="remediation_actions")


class PostmortemRow(Base):
    __tablename__ = "postmortems"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), unique=True)
    summary_markdown: Mapped[str] = mapped_column(String)
    timeline_json: Mapped[list] = mapped_column(JSON, default=list)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    incident: Mapped[Incident] = relationship(back_populates="postmortem")


class AgentTokenUsageRow(Base):
    """Gemini token usage for one agent's one turn, captured from the ADK
    event stream in runner.py -- see docs/agents.md#cost--token-usage for
    the enterprise cost-governance angle this feeds into (per-incident and
    fleet-wide token/cost totals in the analytics API)."""

    __tablename__ = "agent_token_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    agent_name: Mapped[str] = mapped_column(String(32))
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    incident: Mapped[Incident] = relationship(back_populates="token_usage")
