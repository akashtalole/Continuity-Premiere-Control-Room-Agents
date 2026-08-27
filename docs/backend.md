# Backend — FastAPI Service

## REST API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness/readiness probe |
| POST | `/api/simulate/inject-anomaly` | Demo-only: skips telemetry, hands the crew an already-detected anomaly directly |
| POST | `/api/simulate/chaos` | Demo-only: spikes a metric/region in the real synthetic OTel pipeline (the "chaos script") |
| GET | `/api/incidents` | List incidents |
| GET | `/api/incidents/{incident_id}` | Incident detail + full agent timeline |
| POST | `/api/incidents/{incident_id}/approve` | Human approves a pending Responder action |
| POST | `/api/incidents/{incident_id}/reject` | Human rejects a pending Responder action |
| GET | `/api/incidents/{incident_id}/postmortem` | Fetch generated postmortem markdown |
| GET | `/api/agents/status` | Current state of each agent, with the set of incidents it's actively working (idle / running / blocked) |
| GET | `/api/dashboards/panel-image` | Proxies the `get_panel_image` MCP tool result as a PNG |
| GET | `/api/analytics/summary` | Cross-incident stats: totals, status breakdown, MTTR, breach counts by metric/region |
| WS | `/ws/control-room` | Real-time event stream to the frontend (see below) |

## WebSocket event contract

Every push uses the `AgentEventEnvelope` schema (see [`low-level-design.md`](low-level-design.md#pydantic-schemas-backendappmodelsschemaspy)):

```json
{
  "type": "responder_action_pending",
  "incident_id": "1b2e...",
  "agent": "responder",
  "timestamp": "2026-08-22T19:04:11Z",
  "payload": {
    "action_type": "cdn_regional_failover",
    "risk_level": "high",
    "description": "Fail APAC edge traffic over to backup CDN pool."
  }
}
```

## Backend entry point

```python
# backend/app/main.py (abridged -- see the file for the lifespan/DB-init wiring)
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.routers import agents, analytics, dashboards, health, incidents, simulate
from app.services import sentinel_loop
from app.ws.manager import manager

app = FastAPI(title="Premiere Control Room API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["*"], allow_headers=["*"])

app.include_router(health.router)
app.include_router(incidents.router, prefix="/api/incidents", tags=["incidents"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(dashboards.router, prefix="/api/dashboards", tags=["dashboards"])
app.include_router(simulate.router, prefix="/api/simulate", tags=["simulate"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])


@app.websocket("/ws/control-room")
async def control_room_socket(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # heartbeat / no-op from client
    except WebSocketDisconnect:
        manager.disconnect(ws)
```

`lifespan` runs `app.db.init_db()` on startup (creating tables if needed) and starts/stops `app/services/sentinel_loop.py`'s background polling task -- a no-op when the mock crew is active, since it requires real Grafana/Gemini credentials (see [`agents.md`](agents.md#sentinel-background-polling-loop)). `GET /api/agents/status` is backed by `app/services/agent_status.py`, an in-memory registry tracking, per agent, the *set* of incidents it's actively working -- not a single "current incident" -- so overlapping incidents (see [`low-level-design.md`](low-level-design.md#concurrent-incidents)) don't clobber each other's status.

## Approval-gate endpoint (forced function calling in practice)

```python
# backend/app/routers/incidents.py
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.orchestrator import orchestrator

router = APIRouter()


@router.post("/{incident_id}/approve")
async def approve_action(incident_id: UUID) -> dict[str, str]:
    ok = await orchestrator.resolve_pending_approval(incident_id, approved=True, actor="oncall-engineer")
    if not ok:
        raise HTTPException(404, "No pending approval for this incident")
    return {"status": "approved"}


@router.post("/{incident_id}/reject")
async def reject_action(incident_id: UUID) -> dict[str, str]:
    ok = await orchestrator.resolve_pending_approval(incident_id, approved=False, actor="oncall-engineer")
    if not ok:
        raise HTTPException(404, "No pending approval for this incident")
    return {"status": "rejected"}
```

The Responder agent's tool call for any `risk_level == "high"` action always routes through `request_human_approval`, which blocks on an `asyncio.Event` set by this endpoint — the agent cannot proceed past this point on its own, regardless of what the LLM decides. This is the concrete implementation of the hackathon's "Forced Function Calling" pattern and of the "Studio Head enforcing governance" framing. See [`agents.md`](agents.md#the-approval-tool-forced-function-calling) for the tool implementation.
