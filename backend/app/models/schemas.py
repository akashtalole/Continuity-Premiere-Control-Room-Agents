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


# --- REST response shapes -------------------------------------------------


class IncidentSummary(BaseModel):
    id: UUID
    title: str
    status: IncidentStatus
    grafana_incident_id: str | None = None
    opened_at: datetime
    resolved_at: datetime | None = None


class AgentEventRecord(BaseModel):
    id: UUID
    incident_id: UUID
    agent_name: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class AgentTokenUsage(BaseModel):
    agent_name: str
    input_tokens: int
    output_tokens: int


class IncidentDetail(IncidentSummary):
    events: list[AgentEventRecord] = Field(default_factory=list)
    token_usage: list[AgentTokenUsage] = Field(default_factory=list)


class AgentStatus(BaseModel):
    name: Literal["sentinel", "detective", "producer", "responder", "wrap"]
    state: Literal["idle", "running", "blocked"]
    active_incidents: list[UUID] = Field(default_factory=list)


class ApprovalActionResponse(BaseModel):
    status: Literal["approved", "rejected"]


class InjectAnomalyRequest(BaseModel):
    metric_name: str = "rebuffer_ratio"
    observed_value: float = 0.18
    threshold: float = 0.05
    region: str = "us-east-1"


class InjectAnomalyResponse(BaseModel):
    incident_id: UUID


class AnalyticsSummary(BaseModel):
    total_incidents: int
    by_status: dict[str, int]
    mttr_seconds: float | None = None
    breaches_by_metric: dict[str, int]
    breaches_by_region: dict[str, int]
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0


class ChaosRequest(BaseModel):
    metric_name: str = "rebuffer_ratio"
    region: str = "us-east-1"
    duration_seconds: float = 45.0


class ChaosResponse(BaseModel):
    metric_name: str
    region: str
    duration_seconds: float


# --- auth / audit / workspaces --------------------------------------------


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    email: str
    role: Literal["viewer", "operator", "admin"]
    workspace_id: str


class UserSummary(BaseModel):
    id: UUID
    email: str
    role: Literal["viewer", "operator", "admin"]
    workspace_id: str
    active: bool
    created_at: datetime


class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: Literal["viewer", "operator", "admin"] = "viewer"
    workspace_id: str = "default"


class AuditLogEntry(BaseModel):
    id: UUID
    actor_email: str
    action: str
    resource_type: str
    resource_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class WorkspaceSummary(BaseModel):
    id: str
    name: str
    created_at: datetime


class CreateWorkspaceRequest(BaseModel):
    id: str
    name: str
