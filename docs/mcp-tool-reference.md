# Appendix A — Grafana MCP Tool Reference Used in This Project

| Tool | Purpose |
|---|---|
| `query_prometheus` | Instant/range PromQL queries for SLO metrics |
| `query_prometheus_histogram` | Latency percentile breakdowns |
| `list_alert_groups` | Check currently firing alerts |
| `describe_infrastructure` | Service topology and dependencies for root-cause scoping |
| `query_loki_logs` | LogQL queries for error signatures |
| `query_loki_patterns` | Detect common log patterns during correlation |
| `tempo_traceql-search` / `tempo_get-trace` | Pull exemplar traces through the request path |
| `create_incident` / `add_activity_to_incident` | Open and annotate a Grafana Incident |
| `get_current_oncall_users` / `list_oncall_schedules` | Identify who to page |
| `generate_deeplink` | Human-readable link back into Grafana for deeper digging |
| `alerting_manage_rules` | Read/adjust alert rules as part of remediation |
| `create_annotation` | Mark exactly when/where an issue began on a dashboard panel |
| `get_panel_image` | Render a dashboard panel as PNG for the control room UI and postmortem |
| `get_incident` / `get_annotations` / `get_dashboard_summary` | Postmortem assembly |

See [`low-level-design.md`](low-level-design.md#grafana-mcp-tool-mapping) for which agent owns which tools.
