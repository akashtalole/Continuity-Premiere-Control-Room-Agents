from collections import Counter

from fastapi import APIRouter
from sqlalchemy import select

from app.db import session_scope
from app.models.db import AgentTokenUsageRow, AnomalyEventRow, Incident
from app.models.schemas import AnalyticsSummary

router = APIRouter()

# Approximate list price for gemini-flash-latest, per 1K tokens -- for
# order-of-magnitude cost visibility, not an exact bill. Override by editing
# these constants if you're on a different model or pricing tier.
_INPUT_USD_PER_1K = 0.000075
_OUTPUT_USD_PER_1K = 0.0003


@router.get("/summary", response_model=AnalyticsSummary)
async def analytics_summary() -> AnalyticsSummary:
    """Cross-incident analytics for the history page: totals, MTTR, breach
    frequency by metric/region, and fleet-wide Gemini token usage/estimated
    cost (see docs/agents.md#cost--token-usage). Durations are averaged in
    Python rather than in SQL so this works identically on SQLite and
    Postgres."""
    async with session_scope() as db:
        incidents = (await db.execute(select(Incident.status, Incident.opened_at, Incident.resolved_at))).all()
        anomalies = (await db.execute(select(AnomalyEventRow.metric_name, AnomalyEventRow.region))).all()
        usage = (
            await db.execute(select(AgentTokenUsageRow.input_tokens, AgentTokenUsageRow.output_tokens))
        ).all()

    by_status = Counter(status for status, _, _ in incidents)

    durations = [
        (resolved_at - opened_at).total_seconds() for _, opened_at, resolved_at in incidents if resolved_at is not None
    ]
    mttr_seconds = sum(durations) / len(durations) if durations else None

    breaches_by_metric = Counter(metric_name for metric_name, _ in anomalies)
    breaches_by_region = Counter(region for _, region in anomalies)

    total_input_tokens = sum(i for i, _ in usage)
    total_output_tokens = sum(o for _, o in usage)
    estimated_cost_usd = (total_input_tokens / 1000) * _INPUT_USD_PER_1K + (total_output_tokens / 1000) * _OUTPUT_USD_PER_1K

    return AnalyticsSummary(
        total_incidents=len(incidents),
        by_status=dict(by_status),
        mttr_seconds=mttr_seconds,
        breaches_by_metric=dict(breaches_by_metric),
        breaches_by_region=dict(breaches_by_region),
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        estimated_cost_usd=round(estimated_cost_usd, 4),
    )
