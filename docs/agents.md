# Agent Layer — Google ADK

This is the as-built version of the agent layer (`backend/app/adk_agents/`). It differs from the original design sketch in one important way: the spec's draft `agent.run_async(input=...)` call doesn't exist on `google.adk.agents.Agent` in `google-adk` 2.7.x. The real invocation surface is `google.adk.runners.Runner` driven by a `SessionService`, streaming `Event`s back per turn — `runner.py` below wraps that into a one-shot `AgentInvoker.run()` call the orchestrator can await like the spec originally imagined.

## Shared MCP toolset

```python
# backend/app/adk_agents/mcp.py
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from app.config import get_settings


def grafana_toolset(tool_filter: list[str] | None = None) -> McpToolset:
    """Build an MCP toolset connected to Grafana Cloud (or self-hosted mcp-grafana)."""
    settings = get_settings()

    headers: dict[str, str] = {"X-Grafana-URL": settings.grafana_url}
    if settings.grafana_service_account_token:
        headers["Authorization"] = f"Bearer {settings.grafana_service_account_token}"

    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=settings.grafana_mcp_endpoint,
            headers=headers,
        ),
        tool_filter=tool_filter,
    )
```

Each agent gets its own `McpToolset` instance, scoped with `tool_filter` to exactly the MCP tools listed for that agent in [`low-level-design.md`](low-level-design.md#grafana-mcp-tool-mapping) — this is what makes Sentinel/Detective read-only and Producer/Responder the only agents that can reach write tools, enforced by the toolset itself rather than by agent instructions alone.

> For a fully unattended deployment (no one available to complete the one-time browser OAuth), swap this for the open-source `grafana/mcp-grafana` server run alongside the backend, authenticated with a Grafana service-account token instead of interactive OAuth (set `GRAFANA_SERVICE_ACCOUNT_TOKEN`). The hosted `mcp.grafana.com` endpoint has no service-account option.

## Agent definitions

Each agent also declares an `output_schema` — a Pydantic model from `app/models/schemas.py` (or `output_schemas.py` for Sentinel). ADK 2.7's `output_schema` + `tools` combination lets the agent still call MCP tools mid-turn while its final reply is validated against the schema, so the orchestrator gets back structured JSON instead of having to parse free text.

```python
# backend/app/adk_agents/agents.py (abridged; see the file for full tool_filter lists)
from google.adk.agents import Agent

from app.adk_agents.approval import request_human_approval_tool
from app.adk_agents.instructions import (
    DETECTIVE_INSTRUCTION, PRODUCER_INSTRUCTION, RESPONDER_INSTRUCTION,
    SENTINEL_INSTRUCTION, WRAP_INSTRUCTION,
)
from app.adk_agents.mcp import grafana_toolset
from app.adk_agents.output_schemas import SentinelFinding
from app.config import get_settings
from app.models.schemas import IncidentBrief, PostmortemReport, RemediationAction, RootCauseFinding

def build_agent_crew() -> dict[str, Agent]:
    model = get_settings().gemini_model

    sentinel_agent = Agent(
        model=model, name="sentinel", instruction=SENTINEL_INSTRUCTION,
        tools=[grafana_toolset(tool_filter=SENTINEL_TOOLS)],
        output_schema=SentinelFinding,
    )
    detective_agent = Agent(
        model=model, name="detective", instruction=DETECTIVE_INSTRUCTION,
        tools=[grafana_toolset(tool_filter=DETECTIVE_TOOLS)],
        output_schema=RootCauseFinding,
    )
    producer_agent = Agent(
        model=model, name="producer", instruction=PRODUCER_INSTRUCTION,
        tools=[grafana_toolset(tool_filter=PRODUCER_TOOLS)],
        output_schema=IncidentBrief,
    )
    responder_agent = Agent(
        model=model, name="responder", instruction=RESPONDER_INSTRUCTION,
        tools=[grafana_toolset(tool_filter=RESPONDER_TOOLS), request_human_approval_tool],
        output_schema=RemediationAction,
    )
    wrap_agent = Agent(
        model=model, name="wrap", instruction=WRAP_INSTRUCTION,
        tools=[grafana_toolset(tool_filter=WRAP_TOOLS)],
        output_schema=PostmortemReport,
    )
    return {"sentinel": sentinel_agent, "detective": detective_agent, "producer": producer_agent,
            "responder": responder_agent, "wrap": wrap_agent}
```

## The approval tool (forced function calling)

Unchanged from the original design — this is the concrete implementation of the hackathon's "Forced Function Calling" pattern:

```python
# backend/app/adk_agents/approval.py
import asyncio
from uuid import UUID

from google.adk.tools import FunctionTool

_pending: dict[str, asyncio.Future[bool]] = {}


async def request_human_approval(incident_id: str, action_description: str, risk_level: str) -> str:
    """Blocks until a human approves or rejects via POST /incidents/{id}/approve|reject.

    The Responder agent MUST call this before executing any action classified
    as high risk -- its instruction forbids calling any write tool at high
    risk without first getting an "approved" result from this tool.
    """
    future: asyncio.Future[bool] = asyncio.get_event_loop().create_future()
    _pending[incident_id] = future
    try:
        approved = await future
    finally:
        _pending.pop(incident_id, None)
    return "approved" if approved else "rejected"


def resolve_approval(incident_id: UUID | str, approved: bool) -> bool:
    future = _pending.get(str(incident_id))
    if future is None or future.done():
        return False
    future.set_result(approved)
    return True


request_human_approval_tool = FunctionTool(func=request_human_approval)
```

## Runner wrapper

Each agent runs behind one `google.adk.runners.Runner` + `InMemorySessionService` pair, keyed per-incident so agent memory never leaks across incidents:

```python
# backend/app/adk_agents/runner.py (abridged)
import json
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

APP_NAME = "premiere-control-room"
USER_ID = "control-room"

class AgentInvoker:
    def __init__(self, agent):
        self._agent = agent
        self._session_service = InMemorySessionService()
        self._runner = Runner(agent=agent, app_name=APP_NAME, session_service=self._session_service)

    async def run(self, incident_id: str, input_data: dict) -> dict:
        session_id = f"{self._agent.name}-{incident_id}"
        await self._session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
        message = types.Content(role="user", parts=[types.Part(text=json.dumps(input_data, default=str))])

        final_text = None
        async for event in self._runner.run_async(user_id=USER_ID, session_id=session_id, new_message=message):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = "".join(part.text or "" for part in event.content.parts)

        return json.loads(final_text)
```

## Mock crew (no live credentials required)

`app/adk_agents/mock_crew.py` implements the same `Invoker` protocol (`async run(incident_id, input_data) -> dict`) with deterministic synthetic responses, including a real call into `approval.request_human_approval` for the Responder step — so the human-approval gate behaves identically whether or not Gemini/Grafana credentials are configured. `app/adk_agents/crew.py` picks between the two based on `Settings.agents_configured` (true once `GOOGLE_API_KEY` and `GRAFANA_URL` are both set):

```python
# backend/app/adk_agents/crew.py
from functools import lru_cache
from app.adk_agents.mock_crew import Invoker, build_mock_crew
from app.config import get_settings

@lru_cache
def get_crew() -> dict[str, Invoker]:
    settings = get_settings()
    if not settings.agents_configured:
        return build_mock_crew()
    from app.adk_agents.agents import build_agent_crew
    from app.adk_agents.runner import AgentInvoker
    return {name: AgentInvoker(agent) for name, agent in build_agent_crew().items()}
```

This keeps the FastAPI backend, orchestrator, persistence, WebSocket feed, and control room UI fully exercisable end-to-end without live credentials -- useful for local development and for this repo's own CI/demo environment.

## Orchestrator

`app/orchestrator.py` drives one incident through Detective -> Producer -> Responder -> Wrap (Sentinel's detection is the input that starts the run — either the background polling loop below or `POST /api/simulate/inject-anomaly`), persisting each step as an `AGENT_EVENT` row and broadcasting it over the control-room WebSocket. It consults the playbook table (`playbooks.py`, see [`low-level-design.md`](low-level-design.md#remediation-playbook-table)) *before* calling the Responder, so only high-risk actions show the approval-pending UI state:

```python
# backend/app/orchestrator.py (abridged -- see the file for persistence/status-tracking detail)
async def _run_crew(self, incident_id, anomaly):
    crew = get_crew()
    finding = await crew["detective"].run(str(incident_id), anomaly)
    await self._record_agent_event(incident_id, "detective", "detective_finding", finding)

    brief = await crew["producer"].run(str(incident_id), {**anomaly, **finding})
    await self._record_agent_event(incident_id, "producer", "producer_brief", brief)

    playbook = select_playbook(anomaly.get("metric_name"))
    if playbook["risk_level"] == "high":
        await self._emit(incident_id, "responder", "responder_action_pending", {...})
        agent_status.set_state("responder", incident_id, "blocked")
    else:
        agent_status.set_state("responder", incident_id, "running")  # straight to Remediating, no approval hop

    resolution = await crew["responder"].run(str(incident_id), {**anomaly, **brief})  # blocks on approval internally, if high risk
    await self._record_remediation(incident_id, resolution)

    events = await self._events_for_wrap(incident_id)
    postmortem = await crew["wrap"].run(str(incident_id), {"incident_id": str(incident_id), "events": events, ...})
    await self._record_postmortem(incident_id, postmortem)
```

`agent_status.set_state(agent, incident_id, state)` records status per (agent, incident) pair rather than a single current incident, which is what makes overlapping incidents safe -- see [`low-level-design.md`](low-level-design.md#concurrent-incidents).

## Sentinel background polling loop

`app/services/sentinel_loop.py` is the always-on counterpart to the manual `/api/simulate/inject-anomaly` demo endpoint. When `Settings.agents_configured` is true (real `GOOGLE_API_KEY` + `GRAFANA_URL`), FastAPI's `lifespan` starts a background task that, on a timer (`SENTINEL_POLL_INTERVAL_SECONDS`, default 15s), invokes the real Sentinel agent against a small table of SLO thresholds (metric/threshold/region) and calls `orchestrator.start_incident(...)` for each breach it reports -- deduping against incidents already in flight for that metric/region so a slow-to-resolve incident doesn't get re-opened every poll. It's a deliberate no-op in mock mode: without a real Grafana stack there's nothing new for polling to discover over just re-running the deterministic mock crew, so use the simulate endpoint for demos instead.

## Synthetic live streaming pipeline

`app/simulate/otel_pipeline.py` is the "Live streaming pipeline (synthetic)" box from the architecture diagrams, made real: a background task (enabled by default via `SIMULATE_LIVE_PIPELINE`) that emits actual OpenTelemetry metrics, logs, and traces for all five playbook metrics across five regions -- an observable gauge per metric via a callback reading shared in-memory state, a `process_playback_request` trace span per region per tick, and a log record whenever `rebuffer_ratio` runs hot. It exports over OTLP once `OTEL_EXPORTER_OTLP_ENDPOINT` is set (e.g. to Grafana Cloud's OTLP gateway), and falls back to the OpenTelemetry SDK's console exporters otherwise, so `uvicorn app.main:app` alone prints real telemetry to the terminal with no external dependency.

`POST /api/simulate/chaos` (`{"metric_name", "region", "duration_seconds"}`) is the "chaos script" from `docs/build-plan.md`: it calls `otel_pipeline.trigger_chaos(...)`, which spikes that one metric/region combination in the pipeline's state for real, so a real Sentinel agent polling a real Grafana stack (see the polling loop above) would actually find and act on the breach -- as opposed to `/api/simulate/inject-anomaly`, which skips telemetry entirely and hands the crew a pre-made anomaly for quick UI demos.

## Cross-incident memory

`app/adk_agents/memory_tools.py` gives the Detective a `find_similar_incidents(metric_name, limit)` `FunctionTool` -- plain application data, not a vector store or RAG pipeline, since "has this exact metric broken before" is a query, not a semantic search. It looks up past incidents with the same breaching `metric_name` that reached a terminal status, joining in each one's remediation action and postmortem excerpt. `DETECTIVE_INSTRUCTION` tells the agent to call it first and weigh its confidence up or down based on what comes back. `app/adk_agents/mock_crew.py`'s `MockDetectiveInvoker` calls the same lookup function directly (not a canned response), so the "we've seen this before" behavior demos identically without live Gemini/Grafana credentials -- see `tests/test_memory.py`.

## Cost & token usage

`AgentInvoker.run()` (runner.py) reads `event.usage_metadata` (`prompt_token_count` / `candidates_token_count`) off every ADK event and accumulates it into `self.last_usage`; the orchestrator persists that as an `AgentTokenUsageRow` after each agent turn (a no-op for the mock crew's invokers, which never set `last_usage` since they never call a model). `GET /api/incidents/{id}` returns each incident's per-agent breakdown, and `GET /api/analytics/summary` returns fleet-wide totals plus a rough estimated USD cost (list-price constants in `routers/analytics.py`, not a real billing integration) -- surfaced in the frontend's incident timeline and history page.

## Escalation & notifications

`app/services/notifications.py` fans a lifecycle event out to every URL in `NOTIFICATION_WEBHOOK_URLS` as `{"text": "...", ...}` JSON -- the same shape a Slack incoming webhook expects, so Slack needs no separate integration path, just a webhook URL. The orchestrator calls it when an incident starts awaiting approval and when it resolves. Separately, `Orchestrator._escalate_if_unresolved` is spawned alongside the approval-pending state: it sleeps `ESCALATION_TIMEOUT_SECONDS` (default 300s) and, if `approval.has_pending_approval` is still true, sends a second "escalation" notification -- the crew re-pages rather than waiting on a human indefinitely. Both are best-effort: a webhook failure is logged and swallowed, never allowed to break the incident response flow itself.

## Access control & audit log

`app/auth.py` is JWT-based (`pyjwt`), with a three-tier role hierarchy -- viewer < operator < admin -- checked by `require_role(minimum)` as a FastAPI dependency. The control room and history views stay unauthenticated on purpose (a read-only dashboard shouldn't require a login), but `POST /api/incidents/{id}/approve|reject` and `POST /api/simulate/inject-anomaly|chaos` require `operator`+, and user/workspace management requires `admin`. A bootstrap admin is created on first startup from `ADMIN_EMAIL`/`ADMIN_PASSWORD` (a random password is generated and logged once if unset). Every sensitive action is written to `AuditLogRow` via `record_audit()`, visible at `GET /api/audit-log` (and the frontend's `/audit` page) -- including the *real* authenticated approver's email on a remediation, not whatever an LLM's structured output happened to put in its own `approved_by` field (see `approval.take_resolved_by` / `orchestrator._record_remediation`). See [`security.md`](security.md) for the full threat-model writeup.

## Workspaces

`Workspace`/`Incident.workspace_id`/`User.workspace_id` give this a lightweight multi-tenancy boundary: incidents and users belong to exactly one workspace (a `default` one is seeded on first startup), `GET /api/incidents`/`GET /api/workspaces` accept an optional `workspace_id` filter for the frontend's switcher, and `POST /api/simulate/inject-anomaly` always tags the new incident with the *caller's own* workspace_id (not a client-supplied one). This is application-level data isolation, not infrastructure isolation -- there's one shared Grafana MCP connection and one WebSocket broadcast stream across all workspaces; per-workspace Grafana credentials and a workspace-scoped socket are natural follow-ups if that's ever needed.

See [`agent-instructions.md`](agent-instructions.md) for the full instruction text given to each agent, [`low-level-design.md`](low-level-design.md#grafana-mcp-tool-mapping) for which MCP tools each agent is scoped to, and [`backend.md`](backend.md) for how `POST /api/incidents/{id}/approve|reject` resolves the pending `request_human_approval` future.
