from collections import Counter

from fastapi import APIRouter
from sqlalchemy import select

from app.db import session_scope
from app.models.db import AnomalyEventRow, Incident
from app.models.schemas import AnalyticsSummary

router = APIRouter()


@router.get("/summary", response_model=AnalyticsSummary)
async def analytics_summary() -> AnalyticsSummary:
    """Cross-incident analytics for the history page: totals, MTTR, and
    breach frequency by metric/region. Durations are averaged in Python
    rather than in SQL so this works identically on SQLite and Postgres."""
    async with session_scope() as db:
        incidents = (await db.execute(select(Incident.status, Incident.opened_at, Incident.resolved_at))).all()
        anomalies = (await db.execute(select(AnomalyEventRow.metric_name, AnomalyEventRow.region))).all()

    by_status = Counter(status for status, _, _ in incidents)

    durations = [
        (resolved_at - opened_at).total_seconds() for _, opened_at, resolved_at in incidents if resolved_at is not None
    ]
    mttr_seconds = sum(durations) / len(durations) if durations else None

    breaches_by_metric = Counter(metric_name for metric_name, _ in anomalies)
    breaches_by_region = Counter(region for _, region in anomalies)

    return AnalyticsSummary(
        total_incidents=len(incidents),
        by_status=dict(by_status),
        mttr_seconds=mttr_seconds,
        breaches_by_metric=dict(breaches_by_metric),
        breaches_by_region=dict(breaches_by_region),
    )
