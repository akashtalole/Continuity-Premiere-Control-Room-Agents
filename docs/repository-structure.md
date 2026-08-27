# Repository Structure

Actual implementation layout (backend and frontend are both implemented; see [`build-plan.md`](build-plan.md) for how they were sequenced):

```
premiere-control-room/
├── LICENSE
├── README.md
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── .env.example
│   └── app/
│       ├── main.py                 # FastAPI app, router + WS wiring, DB init
│       ├── config.py                # Settings (env vars), agents_configured switch
│       ├── db.py                    # async SQLAlchemy engine/session
│       ├── orchestrator.py          # drives Sentinel(anomaly)->Detective->Producer->Responder->Wrap
│       ├── adk_agents/
│       │   ├── mcp.py               # Grafana Cloud MCP toolset factory
│       │   ├── agents.py            # the 5 google.adk Agent definitions
│       │   ├── crew.py              # picks real ADK crew vs. mock crew
│       │   ├── runner.py            # Runner + InMemorySessionService wrapper
│       │   ├── mock_crew.py         # deterministic crew used without live credentials
│       │   ├── approval.py          # forced-function-calling human approval gate
│       │   ├── playbooks.py         # metric -> {action_type, risk_level, description}
│       │   ├── instructions.py      # per-agent system instructions
│       │   └── output_schemas.py    # structured output schema for Sentinel
│       ├── routers/
│       │   ├── health.py
│       │   ├── incidents.py         # list/detail/approve/reject/postmortem
│       │   ├── agents.py            # GET /api/agents/status
│       │   ├── dashboards.py        # GET /api/dashboards/panel-image
│       │   ├── simulate.py          # POST /api/simulate/inject-anomaly, /chaos
│       │   └── analytics.py         # GET /api/analytics/summary
│       ├── services/
│       │   ├── agent_status.py      # per-incident idle/running/blocked registry
│       │   └── sentinel_loop.py     # background Sentinel polling (real crew only)
│       ├── models/
│       │   ├── schemas.py           # Pydantic wire/API schemas
│       │   └── db.py                # SQLAlchemy ORM tables (ER diagram)
│       ├── ws/
│       │   └── manager.py           # WebSocket connection manager/broadcaster
│       └── simulate/
│           ├── synthetic_pipeline.py  # demo anomaly builder (inject-anomaly)
│           └── otel_pipeline.py       # real OTel metrics/logs/traces + chaos trigger
│   └── tests/                       # pytest suite (see build-plan.md)
│       ├── conftest.py
│       ├── test_playbooks.py
│       ├── test_agent_status.py
│       └── test_incidents_api.py
├── frontend/
│   ├── package.json
│   ├── Dockerfile
│   ├── .env.example
│   └── app/
│       ├── page.tsx                 # ControlRoomPage ("/")
│       ├── layout.tsx
│       ├── history/
│       │   └── page.tsx             # HistoryPage ("/history") -- archive + analytics
│       ├── components/
│       │   ├── LiveQoEMap.tsx
│       │   ├── AgentActivityFeed.tsx
│       │   ├── IncidentTimeline.tsx
│       │   ├── ApprovalModal.tsx    # queues multiple pending approvals
│       │   └── GrafanaPanelEmbed.tsx
│       └── (lib/ is at frontend/lib, shared via the @/ import alias)
│   └── lib/
│       ├── api.ts                   # REST client
│       ├── types.ts                 # shared wire types
│       └── useControlRoomSocket.ts  # WebSocket hook with reconnect/backoff
└── infra/
    ├── cloudrun-backend.yaml
    ├── cloudrun-frontend.yaml
    └── scripts/                      # deploy from Google Cloud Shell -- see infra/scripts/README.md
        ├── lib.sh                    # shared helpers (secrets, Artifact Registry, project resolution)
        ├── 00-setup.sh                # enable APIs, create the Artifact Registry repo
        ├── deploy-backend.sh          # build + deploy the backend
        ├── deploy-frontend.sh         # build + deploy the frontend (needs the backend's URL)
        ├── deploy-all.sh              # runs all of the above, then tightens backend CORS
        ├── provision-cloudsql.sh      # optional: real Postgres persistence
        └── teardown.sh                # delete the Cloud Run services (+ Cloud SQL, optionally)
```

- **`backend/`** — FastAPI service, ADK agent crew, orchestrator, and the synthetic telemetry pipeline used for demos. See [`backend.md`](backend.md) and [`agents.md`](agents.md).
- **`frontend/`** — Next.js control room web app. See [`frontend.md`](frontend.md).
- **`infra/`** — Cloud Run service definitions and the deploy scripts; paired with each app's `Dockerfile`. See [`deployment.md`](deployment.md) and [`infra/scripts/README.md`](../infra/scripts/README.md).

## Running locally

```bash
# Backend (defaults to the deterministic mock crew -- see agents.md -- until
# GOOGLE_API_KEY and GRAFANA_URL are set in backend/.env)
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Then open http://localhost:3000 and click **Inject demo anomaly** to drive a full incident through the crew.

## Running the tests

```bash
cd backend
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Runs against an isolated temp SQLite database and the mock crew -- no live credentials needed. See [`build-plan.md`](build-plan.md#automated-tests).
