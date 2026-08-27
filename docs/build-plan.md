# Build Plan / Milestones

1. **Telemetry stub** — synthetic pipeline emitting OpenTelemetry to Grafana Cloud; confirm data lands in Mimir/Loki/Tempo. ✅ Built: `backend/app/simulate/otel_pipeline.py` emits real metrics/logs/traces (console exporter by default, OTLP export to Grafana Cloud once `OTEL_EXPORTER_OTLP_ENDPOINT` is set — see [`deployment.md`](deployment.md)). Landing the data in Mimir/Loki/Tempo specifically still needs a real Grafana Cloud OTLP endpoint to point it at.
2. **MCP wiring** — Sentinel agent calling `query_prometheus` end-to-end through ADK; verify OAuth flow. ⚠️ Code-complete (`app/adk_agents/mcp.py`, `agents.py`) and verified against the installed `google-adk` package's actual API, but never yet run against a live Grafana Cloud MCP server — this is the top item to close out before submission.
3. **Detective + Producer** — root-cause correlation and incident creation working against real data. ⚠️ Same caveat as #2: real against the mock crew's synthetic findings, unverified against a live Grafana stack.
4. **Responder + approval gate** — implement `request_human_approval`, wire the FastAPI approve/reject endpoints. ✅ Done and tested, including automated coverage in `backend/tests/test_incidents_api.py`.
5. **Control room UI** — WebSocket feed, live map, approval modal. ✅ Done, plus a queued-approval variant for concurrent incidents and a `/history` analytics page.
6. **Wrap agent** — postmortem generation. ✅ Done.
7. **Chaos script** — a script that reliably injects a demo-able failure on cue for the recording. ✅ `POST /api/simulate/chaos` spikes a metric/region in the synthetic pipeline for real (as opposed to `/api/simulate/inject-anomaly`, which fabricates an already-detected incident for quick UI demos without touching telemetry at all).
8. **Record the 3-minute demo video** — real run against the injected failure, not a mockup. 📝 Script ready at [`demo-video-script.md`](demo-video-script.md); not yet recorded.

## Automated tests

`backend/tests/` (pytest + httpx `ASGITransport`, run with `pytest` from `backend/`) covers the playbook table, per-incident agent-status tracking, and the full incident lifecycle over the REST API against the mock crew: high-risk approval, low-risk auto-execution, rejection, concurrent incidents, and analytics. 16 tests, isolated per-run SQLite database, no live credentials required.
