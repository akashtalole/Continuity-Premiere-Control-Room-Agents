from fastapi import APIRouter

from app.models.schemas import AnalyticsSummary
from app.services import incident_store

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
    cost. See app/services/incident_store.py:analytics_summary for the
    Firestore aggregation."""
    summary = await incident_store.analytics_summary()

    total_input_tokens = summary["total_input_tokens"]
    total_output_tokens = summary["total_output_tokens"]
    estimated_cost_usd = (total_input_tokens / 1000) * _INPUT_USD_PER_1K + (total_output_tokens / 1000) * _OUTPUT_USD_PER_1K

    return AnalyticsSummary(
        total_incidents=summary["total_incidents"],
        by_status=summary["by_status"],
        mttr_seconds=summary["mttr_seconds"],
        breaches_by_metric=summary["breaches_by_metric"],
        breaches_by_region=summary["breaches_by_region"],
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        estimated_cost_usd=round(estimated_cost_usd, 4),
    )
