# Non-Functional Requirements

| Requirement | Target |
|---|---|
| Anomaly detection latency (onset → Sentinel alert) | < 15 s |
| End-to-end diagnosis (onset → Producer brief) | < 60 s |
| Approval gate bypass rate for high-risk actions | 0 — enforced in code, not just prompted |
| MCP call failure handling | Retry with backoff; surface "degraded" status in UI rather than silently stalling |
| WebSocket reconnect | Automatic client-side reconnect with backoff |
| Agent self-observability (bonus) | Instrument the crew with the Grafana AI Observability SDK to show token cost/latency/tool-call traces in the demo |
