# Low-Level Design (LLD)

## Incident lifecycle — state machine

```mermaid
stateDiagram-v2
    [*] --> Monitoring
    Monitoring --> AnomalyDetected: Sentinel flags SLO breach
    AnomalyDetected --> Investigating: Detective correlates signals
    Investigating --> Briefed: Producer drafts incident, pages on-call
    Briefed --> AwaitingApproval: Responder proposes high-risk action
    Briefed --> Remediating: Responder executes low-risk action
    AwaitingApproval --> Remediating: human approves
    AwaitingApproval --> Skipped: human rejects
    Remediating --> Resolved: SLO back within bounds
    Skipped --> Monitoring: back to watch mode
    Resolved --> PostmortemReady: Wrap agent drafts postmortem
    PostmortemReady --> [*]
```

## Full incident sequence

```mermaid
sequenceDiagram
    autonumber
    participant Pipe as Live pipeline
    participant Graf as Grafana Cloud (via MCP)
    participant Sent as Sentinel
    participant Det as Detective
    participant Prod as Producer
    participant Resp as Responder
    participant Wrap as Wrap
    participant BE as FastAPI backend
    participant FE as Control room UI
    participant Human as On-call engineer

    Pipe->>Graf: OpenTelemetry metrics / logs / traces
    loop poll interval
        Sent->>Graf: query_prometheus
        Graf-->>Sent: SLO metric values
    end
    Sent->>Sent: detect SLO breach
    Sent->>BE: AnomalyEvent
    BE->>FE: WS sentinel_alert
    BE->>Det: handoff AnomalyEvent
    Det->>Graf: describe_infrastructure / query_loki_logs / tempo_traceql-search
    Graf-->>Det: logs, traces, topology
    Det->>BE: RootCauseFinding
    BE->>FE: WS detective_finding
    BE->>Prod: handoff RootCauseFinding
    Prod->>Graf: create_incident / add_activity_to_incident / get_current_oncall_users
    Prod->>BE: IncidentBrief
    BE->>FE: WS producer_brief
    Graf-->>Human: OnCall page
    BE->>Resp: handoff IncidentBrief
    Resp->>Resp: classify remediation risk
    alt low risk
        Resp->>Graf: execute playbook action
    else high risk
        Resp->>BE: request_human_approval
        BE->>FE: WS responder_action_pending
        Human->>FE: approve / reject
        FE->>BE: POST /incidents/{id}/approve
        BE->>Resp: approval decision
        opt approved
            Resp->>Graf: execute playbook action
        end
    end
    Resp->>Graf: create_annotation
    Resp->>BE: ResolutionEvent
    BE->>FE: WS incident_resolved
    BE->>Wrap: trigger postmortem (async)
    Wrap->>Graf: get_incident / get_annotations
    Wrap->>BE: PostmortemReport
    BE->>FE: WS postmortem_ready
```

## Persisted data model

```mermaid
erDiagram
    INCIDENT ||--o{ ANOMALY_EVENT : contains
    INCIDENT ||--o{ AGENT_EVENT : logs
    INCIDENT ||--o| POSTMORTEM : produces
    INCIDENT ||--o{ REMEDIATION_ACTION : triggers

    INCIDENT {
        uuid id PK
        string title
        string status
        string grafana_incident_id
        timestamp opened_at
        timestamp resolved_at
    }
    ANOMALY_EVENT {
        uuid id PK
        uuid incident_id FK
        string metric_name
        float observed_value
        float threshold
        string region
        timestamp detected_at
    }
    AGENT_EVENT {
        uuid id PK
        uuid incident_id FK
        string agent_name
        string event_type
        string payload_json
        timestamp created_at
    }
    REMEDIATION_ACTION {
        uuid id PK
        uuid incident_id FK
        string action_type
        string risk_level
        string approval_status
        string approved_by
        timestamp executed_at
    }
    POSTMORTEM {
        uuid id PK
        uuid incident_id FK
        string summary_markdown
        string timeline_json
        timestamp generated_at
    }
```

## Pydantic schemas (`backend/app/models/schemas.py`)

```python
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class IncidentStatus(str, Enum):
    monitoring = "monitoring"
    anomaly_detected = "anomaly_detected"
    investigating = "investigating"
    briefed = "briefed"
    awaiting_approval = "awaiting_approval"
    remediating = "remediating"
    resolved = "resolved"
    postmortem_ready = "postmortem_ready"
    skipped = "skipped"


class AnomalyEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    metric_name: str
    observed_value: float
    threshold: float
    region: str
    detected_at: datetime = Field(default_factory=datetime.utcnow)


class RootCauseFinding(BaseModel):
    summary: str
    confidence: float
    upstream_services: list[str]
    supporting_trace_ids: list[str]
    supporting_log_query: str


class IncidentBrief(BaseModel):
    grafana_incident_id: str
    title: str
    plain_language_summary: str
    severity: Literal["sev1", "sev2", "sev3"]
    oncall_user: str | None = None


class RemediationAction(BaseModel):
    action_type: str
    risk_level: Literal["low", "high"]
    description: str
    approval_status: Literal["not_required", "pending", "approved", "rejected"] = "not_required"
    approved_by: str | None = None
    executed_at: datetime | None = None


class PostmortemReport(BaseModel):
    summary_markdown: str
    timeline: list[dict[str, Any]]
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class AgentEventEnvelope(BaseModel):
    """Wire format for every WebSocket push to the control room UI."""

    type: Literal[
        "sentinel_alert",
        "detective_finding",
        "producer_brief",
        "responder_action_pending",
        "responder_action_executed",
        "incident_resolved",
        "postmortem_ready",
    ]
    incident_id: UUID
    agent: Literal["sentinel", "detective", "producer", "responder", "wrap"]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, Any]
```

## Grafana MCP tool mapping

| Agent | MCP tools used | Access level |
|---|---|---|
| Sentinel | `query_prometheus`, `query_prometheus_histogram`, `list_alert_groups` | Read |
| Detective | `describe_infrastructure`, `query_loki_logs`, `query_loki_patterns`, `tempo_traceql-search`, `tempo_get-trace`, `list_prometheus_label_values` | Read |
| Producer | `create_incident`, `add_activity_to_incident`, `get_current_oncall_users`, `list_oncall_schedules`, `generate_deeplink` | Read + Write (incidents) |
| Responder | `alerting_manage_rules`, `create_annotation`, `get_panel_image` | Read + Write (gated by human approval) |
| Wrap | `get_incident`, `get_annotations`, `get_dashboard_summary` | Read |

See [`mcp-tool-reference.md`](mcp-tool-reference.md) for the full tool-by-tool reference and [`agents.md`](agents.md) for how each agent is wired to the shared MCP toolset.

## Remediation playbook table

The Responder doesn't always propose the same action. `app/adk_agents/playbooks.py` maps the breaching metric to a specific action and risk tier, so the orchestrator and mock crew (and, by instruction, the real Responder agent) all pick consistently:

| Metric | Action | Risk | Behavior |
|---|---|---|---|
| `encoder_queue_depth` | `scale_encoder_capacity` | low | Executes directly -- Briefed → Remediating, no approval hop |
| `cache_hit_ratio` | `purge_cdn_cache` | low | Executes directly |
| `rebuffer_ratio` | `cdn_regional_failover` | high | Blocks on `request_human_approval` |
| `origin_error_rate` | `purge_cdn_cache` | high | Blocks on `request_human_approval` |
| `playback_failure_rate` | `rollback_bad_deploy` | high | Blocks on `request_human_approval` |

Any metric not in the table falls back to the `rebuffer_ratio` playbook. The orchestrator consults this table *before* invoking the Responder, so it only shows the approval-pending UI state and sets Sentinel-through-Wrap agent status to `blocked` for high-risk actions -- low-risk ones go straight to `remediating`.

## Concurrent incidents

Multiple incidents can be in flight at once: `Orchestrator.start_incident` fires an independent `asyncio.Task` per incident, so nothing serializes them. Two things had to change to make that safe rather than merely possible:

- **Agent status** (`app/services/agent_status.py`) tracks, per agent, the *set* of incident IDs it's currently working rather than a single `current_incident_id` -- otherwise a second incident reaching "Detective" would silently overwrite the first's status. `GET /api/agents/status` reports `active_incidents: [...]` per agent, and the agent's overall `state` is `blocked` if any of its active incidents are blocked, else `running`.
- **The control room UI** queues approval requests instead of replacing one pending approval with the next (see [`frontend.md`](frontend.md)), and the "Inject 3 concurrent anomalies" demo button exists specifically to exercise this path.

The one place concurrency isn't free is the demo SQLite database, which serializes writes under load; this is fine for a hackathon demo's incident volume; see [`deployment.md`](deployment.md) for switching to Postgres in production.
