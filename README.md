# Premiere Control Room

**Agentic Cinema — The Blockbuster Hackathon**
An agentic reliability engineer for live media premieres, built on the Google Agent Development Kit (ADK), Gemini, and the Grafana Cloud MCP server.

**Track:** Agentic Cinema — Grafana Labs partner track
**Status:** Implemented and verified end-to-end against both the deterministic mock crew and the real crew — real Gemini via Vertex AI, real Grafana Cloud MCP tool calls against a live stack (backend, frontend, synthetic OpenTelemetry pipeline, JWT auth/RBAC, Firestore-backed incident persistence, 26 automated tests). See [Getting started](#getting-started) for running it either way.

[![Open in Cloud Shell](https://gstatic.com/cloudssh/images/open-btn.svg)](https://console.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https://github.com/akashtalole/continuity-premiere-control-room-agents&cloudshell_workspace=.&cloudshell_open_in_editor=infra/scripts/README.md)
[![Docs](https://img.shields.io/badge/docs-akashtalole.github.io-blue)](https://akashtalole.github.io/Continuity-Premiere-Control-Room-Agents/)

**Full documentation, including a [Setup Guide](https://akashtalole.github.io/Continuity-Premiere-Control-Room-Agents/setup-guide/) and [User Guide](https://akashtalole.github.io/Continuity-Premiere-Control-Room-Agents/user-guide/), is published at [akashtalole.github.io/Continuity-Premiere-Control-Room-Agents](https://akashtalole.github.io/Continuity-Premiere-Control-Room-Agents/).**

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
| Persistence | Firestore (incidents/agent events/postmortems/token usage); Postgres/Cloud SQL in prod (SQLite for local/demo) for users/audit-log/workspaces — see [`docs/agents.md`](docs/agents.md#firestore-persistence) |
| Auth | JWT-based, viewer/operator/admin roles, full audit log — see [`docs/security.md`](docs/security.md) |
| Realtime transport | WebSocket (native FastAPI) |
| Paging / incidents | Grafana OnCall + Grafana Incidents (via MCP write tools) |
| Deployment | Cloud Run (frontend + backend + self-hosted Grafana MCP); Vertex AI Agent Engine optional for the agent crew |

## Getting started

The backend runs against a **deterministic mock crew** by default (no Gemini/Grafana credentials required), so the whole app — REST API, WebSocket feed, human-approval gate, and UI — is exercisable out of the box. Set `GOOGLE_API_KEY` and `GRAFANA_URL` in `backend/.env` to switch to the real ADK + Gemini + Grafana Cloud MCP crew (see [`docs/agents.md`](docs/agents.md#mock-crew-no-live-credentials-required)).

Incidents/agent events/postmortems live in Firestore unconditionally (mock crew or not), so start a local emulator first — one extra command, not a GCP account: `cd backend && npx --yes firebase-tools@latest emulators:start --only firestore` (see [Setup Guide → Firestore](https://akashtalole.github.io/Continuity-Premiere-Control-Room-Agents/setup-guide/#firestore)).

```bash
# Backend — http://localhost:8000 (with the Firestore emulator above already running)
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

This builds and deploys both services to Cloud Run, provisions the Firestore database, and creates the dedicated service accounts — see [`infra/scripts/README.md`](infra/scripts/README.md) for connecting real Grafana/Gemini credentials, provisioning Cloud SQL for users/audit-log persistence, provisioning the Grafana SLO dashboard the control room UI embeds a panel from (`infra/scripts/provision-grafana-dashboard.sh`), and tearing down afterward.

## Advanced capabilities

- **Multi-scenario remediation playbooks** — the Responder doesn't always propose the same fix. `backend/app/adk_agents/playbooks.py` maps the breaching metric to a specific action and risk tier (scale encoder capacity, purge CDN cache, roll back a bad deploy, or fail over a region — low-risk actions auto-execute, high-risk ones still gate on human approval). See [`docs/low-level-design.md`](docs/low-level-design.md#remediation-playbook-table).
- **Concurrent incidents** — multiple incidents can be in flight at once; agent status and the approval UI both track them independently instead of one clobbering another. See [`docs/low-level-design.md`](docs/low-level-design.md#concurrent-incidents).
- **Live Sentinel polling loop** — once real Gemini + Grafana credentials are configured, a background task periodically invokes the Sentinel agent against real SLO thresholds instead of relying only on the manual demo endpoint. See [`docs/agents.md`](docs/agents.md#sentinel-background-polling-loop).
- **Incident history & analytics** — a searchable archive of past incidents plus MTTR and breach-frequency stats at `/history`. See [`docs/frontend.md`](docs/frontend.md#history--analytics-page).
- **Real synthetic telemetry** — a background pipeline emits actual OpenTelemetry metrics, logs, and traces for every playbook metric across five regions (console export by default, real OTLP export to Grafana Cloud once configured), plus `POST /api/simulate/chaos` to spike one on demand. See [`docs/agents.md`](docs/agents.md#synthetic-live-streaming-pipeline).
- **Cross-incident memory** — the Detective checks past incidents that breached the same metric before writing its root-cause hypothesis, and weighs its confidence based on what it finds. See [`docs/agents.md`](docs/agents.md#cross-incident-memory).
- **Auth, roles, and audit log** — JWT-based sign-in with viewer/operator/admin roles; every approve/reject/inject-anomaly/user-management action is attributed to the *real* authenticated actor and written to an audit log. See [`docs/security.md`](docs/security.md).
- **Token usage and cost tracking** — every agent turn's Gemini token usage is recorded per incident, with fleet-wide totals and an estimated USD cost on the history page. See [`docs/agents.md`](docs/agents.md#cost-and-token-usage).
- **AI Observability for free** — the agent crew's own LLM calls and Grafana MCP tool calls ride the same OpenTelemetry pipeline, visible in Grafana Cloud's AI Observability app with no extra instrumentation. See [`docs/agents.md`](docs/agents.md#ai-observability-the-agent-crews-own-telemetry-for-free).
- **Automated tests** — 26 pytest tests covering the playbook table, per-incident agent-status tracking, auth/audit, cross-incident memory, and the full incident lifecycle (approval, auto-exec, rejection, concurrency, analytics) over the REST API, run against a real Firestore emulator. Run with `pytest` from `backend/` — see [`docs/repository-structure.md`](docs/repository-structure.md#running-the-tests).
- **Full documentation site** — architecture, agent design, deployment, security model, setup guide, and user guide, published via MkDocs Material to GitHub Pages: [akashtalole.github.io/Continuity-Premiere-Control-Room-Agents](https://akashtalole.github.io/Continuity-Premiere-Control-Room-Agents/).

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
| Must call Grafana Cloud MCP server at runtime | Every agent holds an `McpToolset` connected to a self-hosted `mcp-grafana` server (the hosted `mcp.grafana.com` endpoint is interactive-OAuth-only, so it can't be driven by an unattended backend — see [`docs/agents.md`](docs/agents.md#grafana-mcp-tool-access)) and calls it on every turn — verified end-to-end against a live Grafana Cloud stack |
| Must use `google-adk` / `google-genai` / `google-cloud-aiplatform` at runtime | All five agents are `google.adk.agents.Agent` instances |
| No non-Google AI frameworks or models | No LangChain, no third-party LLM SDKs anywhere in the stack |
| Must run on web, Android, or iOS | Control room is a web app (Next.js) |
| New project, built during contest period | Spec starts from zero — no reused code |

## License

See [LICENSE](LICENSE).
