"""Cross-incident memory: lets the Detective (and the mock crew's stand-in
for it) check whether a breach has happened before and reuse what the crew
already learned, instead of re-investigating from a blank slate every time.

This is a real Firestore read (app/services/incident_store.py, the same
store the orchestrator writes every incident to), not a vector store or
RAG pipeline -- "has this exact metric broken before, and what did we do
about it" doesn't need semantic search, just a query.
See docs/agents.md#cross-incident-memory.
"""

from typing import Any

from google.adk.tools import FunctionTool

from app.services import incident_store


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
    return await incident_store.find_similar_incidents(metric_name, limit)


find_similar_incidents_tool = FunctionTool(func=find_similar_incidents)
