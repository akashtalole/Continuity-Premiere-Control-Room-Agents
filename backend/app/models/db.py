import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="monitoring")
    grafana_incident_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
