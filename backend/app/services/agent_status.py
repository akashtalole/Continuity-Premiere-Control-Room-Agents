"""In-memory "what is each agent doing right now" registry, backing
GET /api/agents/status. Updated by the orchestrator as it drives an
incident through the crew; not persisted, since it's presence/liveness
state rather than incident history (that lives in AGENT_EVENT rows).

Each agent tracks a *set* of incidents it's currently working (keyed by
incident id -> per-incident state), not a single current_incident_id --
several incidents can be in flight at once (see docs/low-level-design.md's
concurrent-incidents note), and a single "current incident" field would
have one incident's status silently clobber another's.
"""

from typing import Literal
from uuid import UUID

AgentName = Literal["sentinel", "detective", "producer", "responder", "wrap"]
AgentState = Literal["idle", "running", "blocked"]

AGENT_NAMES: tuple[AgentName, ...] = ("sentinel", "detective", "producer", "responder", "wrap")

_active: dict[AgentName, dict[str, AgentState]] = {name: {} for name in AGENT_NAMES}


def set_state(agent: AgentName, incident_id: UUID | str, state: AgentState) -> None:
    key = str(incident_id)
    if state == "idle":
        _active[agent].pop(key, None)
    else:
        _active[agent][key] = state


def clear_incident(incident_id: UUID | str) -> None:
    """Remove an incident from every agent's active set, e.g. after a crew-run failure."""
    key = str(incident_id)
    for agent in AGENT_NAMES:
        _active[agent].pop(key, None)


def snapshot() -> dict[AgentName, dict]:
    result: dict[AgentName, dict] = {}
    for agent in AGENT_NAMES:
        incidents = _active[agent]
        if not incidents:
            result[agent] = {"state": "idle", "active_incidents": []}
        else:
            state: AgentState = "blocked" if "blocked" in incidents.values() else "running"
            result[agent] = {"state": state, "active_incidents": list(incidents.keys())}
    return result
