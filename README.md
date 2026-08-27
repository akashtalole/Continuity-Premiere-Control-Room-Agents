# Premiere Control Room

**Agentic Cinema — The Blockbuster Hackathon**
An agentic reliability engineer for live media premieres, built on the Google Agent Development Kit (ADK), Gemini, and the Grafana Cloud MCP server.

**Track:** Agentic Cinema — Grafana Labs partner track
**Status:** Implemented and tested end-to-end against the deterministic mock crew (backend, frontend, synthetic OpenTelemetry pipeline, 16 automated tests). **Not yet verified against a live Grafana Cloud MCP server or real Gemini** — the code path is real (`McpToolset`, `output_schema`, verified against the installed `google-adk` API), but has never made an actual live call. See [Getting started](#getting-started) and [`docs/build-plan.md`](docs/build-plan.md) for exactly what's open.

[![Open in Cloud Shell](https://gstatic.com/cloudssh/images/open-btn.svg)](https://console.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https://github.com/akashtalole/continuity-premiere-control-room-agents&cloudshell_workspace=.&cloudshell_open_in_editor=infra/scripts/README.md)

---

## What this is

Live, unrepeatable media events (global streaming premieres, award shows, live sports simulcasts) generate traffic spikes that regularly break delivery pipelines — CDN edge overload, encoder saturation, origin latency. Today the response is manual: an engineer stares at a wall of Grafana dashboards, greps logs by hand, and pages people ad hoc. Minutes of triage translate directly into buffering fans and an incident that can never be "re-aired."

**Premiere Control Room** replaces that manual loop with a crew of five ADK agents — **Sentinel, Detective, Producer, Responder, Wrap** — that share one Grafana Cloud MCP connection and automate the detect → correlate → brief → remediate → document loop, with a forced human-approval gate before any state-changing action. A FastAPI backend orchestrates the crew and streams every step to a real-time "control room" web dashboard.

## Agent crew

| Agent | Role |
|---|---|
| **Sentinel** | Continuously monitors SLOs (rebuffer ratio, playback failure rate, origin error rate, encoder queue depth) and detects anomalies |
| **Detective** | Correlates signals across metrics, logs, and traces to build a root-cause hypothesis |
| **Producer** | Turns the finding into an executive-friendly incident brief and pages on-call |
| **Responder** | Proposes and executes remediation — high-risk actions always wait for human approval |
| **Wrap** | Generates the incident timeline and postmortem report |

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (React, TypeScript), Tailwind CSS, native WebSocket client |
| Backend API | FastAPI (Python 3.11+), Uvicorn, Pydantic v2 |
| Agent runtime | Google Agent Development Kit (`google-adk`) |
| LLM | Gemini via Gemini Enterprise Agent Platform / Vertex AI |
| Observability integration | Grafana Cloud MCP server (`grafana/mcp-grafana`, or hosted `mcp.grafana.com`) |
| Persistence | PostgreSQL (Cloud SQL) in prod, SQLite for local/demo |
| Realtime transport | WebSocket (native FastAPI) |
| Paging / incidents | Grafana OnCall + Grafana Incidents (via MCP write tools) |
| Deployment | Cloud Run (frontend + backend); Vertex AI Agent Engine optional for the agent crew |

## Getting started

The backend runs against a **deterministic mock crew** by default (no Gemini/Grafana credentials required), so the whole app — REST API, WebSocket feed, human-approval gate, and UI — is exercisable out of the box. Set `GOOGLE_API_KEY` and `GRAFANA_URL` in `backend/.env` to switch to the real ADK + Gemini + Grafana Cloud MCP crew (see [`docs/agents.md`](docs/agents.md#mock-crew-no-live-credentials-required)).

```bash
# Backend — http://localhost:8000
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn app.main:app --reload --port 8000

# Frontend — http://localhost:3000
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000 and click **Inject demo anomaly** to drive a full incident (Sentinel → Detective → Producer → Responder → Wrap) through the crew, including the approval modal. Click **Inject 3 concurrent anomalies** to see several incidents run in parallel, and visit **History & analytics** (or `/history`) for the incident archive and MTTR/breach stats.

### Deploying to Google Cloud

For a live demo URL instead of localhost, from [Cloud Shell](https://cloud.google.com/shell) (button above) or any machine with `gcloud` authenticated:

```bash
gcloud config set project <YOUR_PROJECT_ID>
bash infra/scripts/deploy-all.sh
```

This builds and deploys both services to Cloud Run — see [`infra/scripts/README.md`](infra/scripts/README.md) for connecting real Grafana/Gemini credentials, provisioning Cloud SQL for real persistence, and tearing down afterward.

## Advanced capabilities

- **Multi-scenario remediation playbooks** — the Responder doesn't always propose the same fix. `backend/app/adk_agents/playbooks.py` maps the breaching metric to a specific action and risk tier (scale encoder capacity, purge CDN cache, roll back a bad deploy, or fail over a region — low-risk actions auto-execute, high-risk ones still gate on human approval). See [`docs/low-level-design.md`](docs/low-level-design.md#remediation-playbook-table).
- **Concurrent incidents** — multiple incidents can be in flight at once; agent status and the approval UI both track them independently instead of one clobbering another. See [`docs/low-level-design.md`](docs/low-level-design.md#concurrent-incidents).
- **Live Sentinel polling loop** — once real Gemini + Grafana credentials are configured, a background task periodically invokes the Sentinel agent against real SLO thresholds instead of relying only on the manual demo endpoint. See [`docs/agents.md`](docs/agents.md#sentinel-background-polling-loop).
- **Incident history & analytics** — a searchable archive of past incidents plus MTTR and breach-frequency stats at `/history`. See [`docs/frontend.md`](docs/frontend.md#history--analytics-page).
- **Real synthetic telemetry** — a background pipeline emits actual OpenTelemetry metrics, logs, and traces for every playbook metric across five regions (console export by default, real OTLP export to Grafana Cloud once configured), plus `POST /api/simulate/chaos` to spike one on demand. See [`docs/agents.md`](docs/agents.md#synthetic-live-streaming-pipeline).
- **Automated tests** — 16 pytest tests covering the playbook table, per-incident agent-status tracking, and the full incident lifecycle (approval, auto-exec, rejection, concurrency, analytics) over the REST API. Run with `pytest` from `backend/` — see [`docs/repository-structure.md`](docs/repository-structure.md#running-the-tests).

## Documentation

Full technical design lives in [`docs/`](docs/):

| Doc | Contents |
|---|---|
| [`docs/overview.md`](docs/overview.md) | Problem statement, goals/non-goals, hackathon constraints |
| [`docs/architecture.md`](docs/architecture.md) | High-level design: system context, containers, technology stack |
| [`docs/low-level-design.md`](docs/low-level-design.md) | Incident state machine, sequence diagram, data model, Pydantic schemas, MCP tool mapping |
| [`docs/backend.md`](docs/backend.md) | FastAPI REST/WebSocket API, approval-gate endpoint |
| [`docs/agents.md`](docs/agents.md) | ADK agent definitions, shared MCP toolset, forced-function-calling approval tool, orchestrator |
| [`docs/frontend.md`](docs/frontend.md) | Control room web app component tree and WebSocket hook |
| [`docs/deployment.md`](docs/deployment.md) | Deployment architecture, environment variables |
| [`docs/security.md`](docs/security.md) | Security and governance model |
| [`docs/non-functional-requirements.md`](docs/non-functional-requirements.md) | Latency, reliability, and observability targets |
| [`docs/repository-structure.md`](docs/repository-structure.md) | Repo layout and local run instructions |
| [`docs/build-plan.md`](docs/build-plan.md) | Milestones for the hackathon build |
| [`docs/mcp-tool-reference.md`](docs/mcp-tool-reference.md) | Grafana MCP tools used, by purpose |
| [`docs/agent-instructions.md`](docs/agent-instructions.md) | System instruction text for each agent |
| [`docs/demo-video-script.md`](docs/demo-video-script.md) | Shot-by-shot script for the 3-minute submission video |

## Hackathon constraints this design satisfies

| Constraint | How |
|---|---|
| Must call Grafana Cloud MCP server at runtime | Every agent holds an `McpToolset` connected to `mcp.grafana.com` (or self-hosted `mcp-grafana`) and calls it on every turn — code-complete and verified against the installed `google-adk` API, **but not yet exercised against a live MCP server** (see `docs/build-plan.md`) |
| Must use `google-adk` / `google-genai` / `google-cloud-aiplatform` at runtime | All five agents are `google.adk.agents.Agent` instances |
| No non-Google AI frameworks or models | No LangChain, no third-party LLM SDKs anywhere in the stack |
| Must run on web, Android, or iOS | Control room is a web app (Next.js) |
| New project, built during contest period | Spec starts from zero — no reused code |

## License

See [LICENSE](LICENSE).
