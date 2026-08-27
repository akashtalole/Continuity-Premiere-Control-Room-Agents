"""Selects the real ADK crew or the deterministic mock crew based on config.

Both expose the same Invoker protocol (async run(incident_id, input_data) ->
dict), so app/orchestrator.py never needs to know which one it's driving.
"""

from functools import lru_cache

from app.adk_agents.mock_crew import Invoker, build_mock_crew
from app.config import get_settings


@lru_cache
def get_crew() -> dict[str, Invoker]:
    settings = get_settings()
    if not settings.agents_configured:
        return build_mock_crew()

    from app.adk_agents.agents import build_agent_crew
    from app.adk_agents.runner import AgentInvoker

    agents = build_agent_crew()
    return {name: AgentInvoker(agent) for name, agent in agents.items()}
