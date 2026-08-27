from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import session_scope
from app.models.db import Incident
from app.models.schemas import (
    AgentEventRecord,
    ApprovalActionResponse,
    IncidentDetail,
    IncidentSummary,
    PostmortemReport,
)
from app.orchestrator import orchestrator

router = APIRouter()


@router.get("", response_model=list[IncidentSummary])
async def list_incidents() -> list[IncidentSummary]:
    async with session_scope() as db:
        rows = (await db.execute(select(Incident).order_by(Incident.opened_at.desc()))).scalars()
        return [
            IncidentSummary(
                id=UUID(r.id),
                title=r.title,
                status=r.status,
                grafana_incident_id=r.grafana_incident_id,
                opened_at=r.opened_at,
                resolved_at=r.resolved_at,
            )
            for r in rows
        ]


@router.get("/{incident_id}", response_model=IncidentDetail)
async def get_incident(incident_id: UUID) -> IncidentDetail:
    async with session_scope() as db:
        incident = await db.get(Incident, str(incident_id), options=[selectinload(Incident.agent_events)])
        if incident is None:
            raise HTTPException(404, "Incident not found")
        events = sorted(incident.agent_events, key=lambda e: e.created_at)
        return IncidentDetail(
            id=UUID(incident.id),
            title=incident.title,
            status=incident.status,
            grafana_incident_id=incident.grafana_incident_id,
            opened_at=incident.opened_at,
            resolved_at=incident.resolved_at,
            events=[
                AgentEventRecord(
                    id=UUID(e.id),
                    incident_id=UUID(e.incident_id),
                    agent_name=e.agent_name,
                    event_type=e.event_type,
                    payload=e.payload_json,
                    created_at=e.created_at,
                )
                for e in events
            ],
        )


@router.get("/{incident_id}/postmortem", response_model=PostmortemReport)
async def get_postmortem(incident_id: UUID) -> PostmortemReport:
    async with session_scope() as db:
        incident = await db.get(Incident, str(incident_id), options=[selectinload(Incident.postmortem)])
        if incident is None or incident.postmortem is None:
            raise HTTPException(404, "Postmortem not yet available for this incident")
        pm = incident.postmortem
        return PostmortemReport(
            summary_markdown=pm.summary_markdown,
            timeline=pm.timeline_json,
            generated_at=pm.generated_at,
        )


@router.post("/{incident_id}/approve", response_model=ApprovalActionResponse)
async def approve_action(incident_id: UUID) -> ApprovalActionResponse:
    ok = await orchestrator.resolve_pending_approval(incident_id, approved=True, actor="oncall-engineer")
    if not ok:
        raise HTTPException(404, "No pending approval for this incident")
    return ApprovalActionResponse(status="approved")


@router.post("/{incident_id}/reject", response_model=ApprovalActionResponse)
async def reject_action(incident_id: UUID) -> ApprovalActionResponse:
    ok = await orchestrator.resolve_pending_approval(incident_id, approved=False, actor="oncall-engineer")
    if not ok:
        raise HTTPException(404, "No pending approval for this incident")
    return ApprovalActionResponse(status="rejected")
