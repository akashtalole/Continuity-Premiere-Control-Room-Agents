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

    headers: dict[str, str] = {}
    if settings.grafana_mcp_server_token:
        # Self-hosted grafana/mcp-grafana (infra/scripts/deploy-mcp-grafana.sh),
        # single-tenant: it already knows which Grafana stack to talk to from
        # its own GRAFANA_URL/GRAFANA_SERVICE_ACCOUNT_TOKEN env vars, so this
        # backend never handles the Grafana credential itself for MCP calls --
        # it only presents the separate caller-auth token mcp-grafana was
        # started with (--server-auth-token / MCP_GRAFANA_SERVER_TOKEN).
        headers["Authorization"] = f"Bearer {settings.grafana_mcp_server_token}"
    else:
        # Hosted mcp.grafana.com: multi-tenant, routes by X-Grafana-URL, and
        # only accepts an interactive OAuth 2.1 session -- there's no
        # service-account path, so this only works if something already
        # completed that browser flow out-of-band. Not viable for an
        # unattended Cloud Run deployment; see docs/agents.md.
        headers["X-Grafana-URL"] = settings.grafana_url

    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=settings.grafana_mcp_endpoint,
            headers=headers,
        ),
        tool_filter=tool_filter,
    )
