"""The five-agent ADK crew: Sentinel, Detective, Producer, Responder, Wrap.

Each agent holds its own Grafana Cloud MCP toolset (see mcp.py) so tool
calls are attributed per-agent in Grafana's own audit surface, but they all
point at one Grafana stack -- see docs/low-level-design.md#grafana-mcp-tool-mapping
for the tool-to-agent scoping this module implements via tool_filter.
"""

from google.adk.agents import Agent

from app.adk_agents.approval import request_human_approval_tool
from app.adk_agents.instructions import (
    DETECTIVE_INSTRUCTION,
    PRODUCER_INSTRUCTION,
    RESPONDER_INSTRUCTION,
    SENTINEL_INSTRUCTION,
    WRAP_INSTRUCTION,
)
from app.adk_agents.mcp import grafana_toolset
from app.adk_agents.output_schemas import SentinelFinding
from app.config import get_settings
from app.models.schemas import IncidentBrief, PostmortemReport, RemediationAction, RootCauseFinding

SENTINEL_TOOLS = ["query_prometheus", "query_prometheus_histogram", "list_alert_groups"]
DETECTIVE_TOOLS = [
    "describe_infrastructure",
    "query_loki_logs",
    "query_loki_patterns",
    "tempo_traceql-search",
    "tempo_get-trace",
    "list_prometheus_label_values",
]
PRODUCER_TOOLS = [
    "create_incident",
    "add_activity_to_incident",
    "get_current_oncall_users",
    "list_oncall_schedules",
    "generate_deeplink",
]
RESPONDER_TOOLS = ["alerting_manage_rules", "create_annotation", "get_panel_image"]
WRAP_TOOLS = ["get_incident", "get_annotations", "get_dashboard_summary"]


def build_agent_crew() -> dict[str, Agent]:
    """Construct the five agents. Call once per process; agents are stateless
    between invocations, with session state carried by the ADK Runner."""
    model = get_settings().gemini_model

    sentinel_agent = Agent(
        model=model,
        name="sentinel",
        description="Monitors live-event SLOs and flags anomalies.",
        instruction=SENTINEL_INSTRUCTION,
        tools=[grafana_toolset(tool_filter=SENTINEL_TOOLS)],
        output_schema=SentinelFinding,
    )

    detective_agent = Agent(
        model=model,
        name="detective",
        description="Correlates metrics, logs, and traces to a root-cause hypothesis.",
        instruction=DETECTIVE_INSTRUCTION,
        tools=[grafana_toolset(tool_filter=DETECTIVE_TOOLS)],
        output_schema=RootCauseFinding,
    )

    producer_agent = Agent(
        model=model,
        name="producer",
        description="Turns a root-cause finding into an executive incident brief.",
        instruction=PRODUCER_INSTRUCTION,
        tools=[grafana_toolset(tool_filter=PRODUCER_TOOLS)],
        output_schema=IncidentBrief,
    )

    responder_agent = Agent(
        model=model,
        name="responder",
        description="Proposes and executes remediation, gated by human approval.",
        instruction=RESPONDER_INSTRUCTION,
        tools=[grafana_toolset(tool_filter=RESPONDER_TOOLS), request_human_approval_tool],
        output_schema=RemediationAction,
    )

    wrap_agent = Agent(
        model=model,
        name="wrap",
        description="Assembles the incident timeline into a postmortem report.",
        instruction=WRAP_INSTRUCTION,
        tools=[grafana_toolset(tool_filter=WRAP_TOOLS)],
        output_schema=PostmortemReport,
    )

    return {
        "sentinel": sentinel_agent,
        "detective": detective_agent,
        "producer": producer_agent,
        "responder": responder_agent,
        "wrap": wrap_agent,
    }
