"""Shared Grafana Cloud MCP connection, reused by every agent in the crew.

A fresh McpToolset is created per agent because each ADK agent owns its own
tool/session lifecycle, but they all point at the same Grafana Cloud MCP
endpoint and stack -- see docs/agents.md and docs/security.md for the
least-privilege rationale (Sentinel/Detective are read-only by instruction;
Producer/Responder are the only agents whose instructions call write tools).
"""

from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from app.config import get_settings


def grafana_toolset(tool_filter: list[str] | None = None) -> McpToolset:
    """Build an MCP toolset connected to Grafana Cloud (or self-hosted mcp-grafana).

    Args:
        tool_filter: optional allow-list of MCP tool names, used to enforce
            least privilege per agent (e.g. Sentinel only gets read tools).
    """
    settings = get_settings()

    headers: dict[str, str] = {"X-Grafana-URL": settings.grafana_url}
    if settings.grafana_service_account_token:
        # Self-hosted grafana/mcp-grafana, authenticated with a service
        # account token instead of the hosted server's interactive OAuth.
        headers["Authorization"] = f"Bearer {settings.grafana_service_account_token}"

    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=settings.grafana_mcp_endpoint,
            headers=headers,
        ),
        tool_filter=tool_filter,
    )
