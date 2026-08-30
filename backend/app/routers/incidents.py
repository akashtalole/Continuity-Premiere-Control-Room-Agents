from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth import CurrentUser, record_audit, require_role
from app.models.schemas import (
    AgentEventRecord,
    AgentTokenUsage,
    ApprovalActionResponse,
    IncidentDetail,
    IncidentSummary,
    PostmortemReport,
)
from app.orchestrator import orchestrator
from app.services import incident_store

router = APIRouter()


@router.get("", response_model=list[IncidentSummary])
async def list_incidents(workspace_id: str | None = None) -> list[IncidentSummary]:
    """Unauthenticated on purpose -- the control room's live view is a
    read-only dashboard; taking action (approve/reject/inject) is what
    requires signing in. See docs/security.md. `workspace_id` is an
    optional filter for the frontend's workspace switcher; omitted, this
    returns every workspace's incidents (today's default single-workspace
    behavior, unchanged)."""
    incidents = await incident_store.list_incidents(workspace_id)
    return [
        IncidentSummary(
            id=UUID(i["id"]),
            title=i["title"],
            status=i["status"],
            grafana_incident_id=i.get("grafana_incident_id"),
            opened_at=i["opened_at"],
            resolved_at=i.get("resolved_at"),
        )
        for i in incidents
    ]


@router.get("/{incident_id}", response_model=IncidentDetail)
async def get_incident(incident_id: UUID) -> IncidentDetail:
    incident = await incident_store.get_incident(str(incident_id))
    if incident is None:
        raise HTTPException(404, "Incident not found")
    return IncidentDetail(
        id=UUID(incident["id"]),
        title=incident["title"],
        status=incident["status"],
        grafana_incident_id=incident.get("grafana_incident_id"),
        opened_at=incident["opened_at"],
        resolved_at=incident.get("resolved_at"),
        events=[
            AgentEventRecord(
                id=UUID(e["id"]),
                incident_id=incident_id,
                agent_name=e["agent_name"],
                event_type=e["event_type"],
                payload=e["payload"],
                created_at=e["created_at"],
            )
            for e in incident["events"]
        ],
        token_usage=[
            AgentTokenUsage(
                agent_name=u["agent_name"], input_tokens=u["input_tokens"], output_tokens=u["output_tokens"]
            )
            for u in incident["token_usage"]
        ],
    )


@router.get("/{incident_id}/postmortem", response_model=PostmortemReport)
async def get_postmortem(incident_id: UUID) -> PostmortemReport:
    pm = await incident_store.get_postmortem(str(incident_id))
    if pm is None:
        raise HTTPException(404, "Postmortem not yet available for this incident")
    return PostmortemReport(summary_markdown=pm["summary_markdown"], timeline=pm["timeline"], generated_at=pm["generated_at"])


@router.get("/{incident_id}/postmortem/export")
async def export_postmortem(incident_id: UUID) -> Response:
    """Same content as GET /postmortem, as a downloadable .md file -- for
    pasting into an incident-review doc or attaching to a ticket."""
    pm = await incident_store.get_postmortem(str(incident_id))
    if pm is None:
        raise HTTPException(404, "Postmortem not yet available for this incident")
    return Response(
        content=pm["summary_markdown"],
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
