"""Cross-incident memory: lets the Detective (and the mock crew's stand-in
for it) check whether a breach has happened before and reuse what the crew
already learned, instead of re-investigating from a blank slate every time.

This is plain application data (the same Postgres/SQLite store everything
else in this app uses), not a vector store or RAG pipeline -- "has this
exact metric broken before, and what did we do about it" doesn't need
semantic search, just a query. See docs/agents.md#cross-incident-memory.
"""

from typing import Any

from google.adk.tools import FunctionTool
from sqlalchemy import select

from app.db import session_scope
from app.models.db import AnomalyEventRow, Incident, PostmortemRow, RemediationActionRow

_TERMINAL_STATUSES = ("postmortem_ready", "resolved", "skipped")


async def _lookup(metric_name: str, limit: int) -> list[dict[str, Any]]:
    async with session_scope() as db:
        rows = (
            await db.execute(
                select(Incident, RemediationActionRow, PostmortemRow)
                .join(AnomalyEventRow, AnomalyEventRow.incident_id == Incident.id)
                .outerjoin(RemediationActionRow, RemediationActionRow.incident_id == Incident.id)
                .outerjoin(PostmortemRow, PostmortemRow.incident_id == Incident.id)
                .where(AnomalyEventRow.metric_name == metric_name)
                .where(Incident.status.in_(_TERMINAL_STATUSES))
                .order_by(Incident.opened_at.desc())
                .limit(limit)
            )
        ).all()

    results: list[dict[str, Any]] = []
    for incident, remediation, postmortem in rows:
        summary = (postmortem.summary_markdown[:400] if postmortem else "") or ""
        results.append(
            {
                "title": incident.title,
                "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
                "action_taken": remediation.action_type if remediation else None,
                "approval_status": remediation.approval_status if remediation else None,
                "postmortem_excerpt": summary,
            }
        )
    return results


async def find_similar_incidents(metric_name: str, limit: int = 3) -> list[dict[str, Any]]:
    """Look up past resolved incidents that involved the same breaching
    metric, across all regions, most recent first. Use this before writing
    your root-cause hypothesis to check whether this is a recurring failure
    mode -- if so, reference what was tried before (and whether it worked)
    rather than starting from a blank slate.

    Args:
        metric_name: the SLO metric name to search for (e.g. "rebuffer_ratio").
        limit: maximum number of past incidents to return (default 3).

    Returns:
        A list of objects with title, resolved_at, action_taken,
        approval_status, and a short postmortem_excerpt for each matching
        past incident, most recent first. Empty list if this metric has
        never breached before.
    """
    return await _lookup(metric_name, limit)


find_similar_incidents_tool = FunctionTool(func=find_similar_incidents)
