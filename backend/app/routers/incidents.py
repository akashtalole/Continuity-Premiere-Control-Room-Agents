from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth import CurrentUser, record_audit, require_role
from app.db import session_scope
from app.models.db import Incident
from app.models.schemas import (
    AgentEventRecord,
    AgentTokenUsage,
    ApprovalActionResponse,
    IncidentDetail,
    IncidentSummary,
    PostmortemReport,
)
from app.orchestrator import orchestrator

router = APIRouter()


@router.get("", response_model=list[IncidentSummary])
async def list_incidents(workspace_id: str | None = None) -> list[IncidentSummary]:
    """Unauthenticated on purpose -- the control room's live view is a
    read-only dashboard; taking action (approve/reject/inject) is what
    requires signing in. See docs/security.md. `workspace_id` is an
    optional filter for the frontend's workspace switcher; omitted, this
    returns every workspace's incidents (today's default single-workspace
    behavior, unchanged)."""
    async with session_scope() as db:
        query = select(Incident).order_by(Incident.opened_at.desc())
        if workspace_id:
            query = query.where(Incident.workspace_id == workspace_id)
        rows = (await db.execute(query)).scalars()
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
        incident = await db.get(
            Incident,
            str(incident_id),
            options=[selectinload(Incident.agent_events), selectinload(Incident.token_usage)],
        )
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
            token_usage=[
                AgentTokenUsage(agent_name=u.agent_name, input_tokens=u.input_tokens, output_tokens=u.output_tokens)
                for u in incident.token_usage
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


@router.get("/{incident_id}/postmortem/export")
async def export_postmortem(incident_id: UUID) -> Response:
    """Same content as GET /postmortem, as a downloadable .md file -- for
    pasting into an incident-review doc or attaching to a ticket."""
    async with session_scope() as db:
        incident = await db.get(Incident, str(incident_id), options=[selectinload(Incident.postmortem)])
        if incident is None or incident.postmortem is None:
            raise HTTPException(404, "Postmortem not yet available for this incident")
        markdown = incident.postmortem.summary_markdown
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="postmortem-{incident_id}.md"'},
    )


@router.post("/{incident_id}/approve", response_model=ApprovalActionResponse)
async def approve_action(
    incident_id: UUID, current: CurrentUser = Depends(require_role("operator"))
) -> ApprovalActionResponse:
    ok = await orchestrator.resolve_pending_approval(incident_id, approved=True, actor=current.email)
    if not ok:
        raise HTTPException(404, "No pending approval for this incident")
    await record_audit(current.email, "approve_remediation", "incident", str(incident_id))
    return ApprovalActionResponse(status="approved")


@router.post("/{incident_id}/reject", response_model=ApprovalActionResponse)
async def reject_action(
    incident_id: UUID, current: CurrentUser = Depends(require_role("operator"))
) -> ApprovalActionResponse:
    ok = await orchestrator.resolve_pending_approval(incident_id, approved=False, actor=current.email)
    if not ok:
        raise HTTPException(404, "No pending approval for this incident")
    await record_audit(current.email, "reject_remediation", "incident", str(incident_id))
    return ApprovalActionResponse(status="rejected")
