export type AgentName = "sentinel" | "detective" | "producer" | "responder" | "wrap";

export type AgentEventType =
  | "sentinel_alert"
  | "detective_finding"
  | "producer_brief"
  | "responder_action_pending"
  | "responder_action_executed"
  | "incident_resolved"
  | "postmortem_ready";

export type AgentEvent = {
  type: AgentEventType;
  incident_id: string;
  agent: AgentName;
  timestamp: string;
  payload: Record<string, unknown>;
};

export type IncidentStatus =
  | "monitoring"
  | "anomaly_detected"
  | "investigating"
  | "briefed"
  | "awaiting_approval"
  | "remediating"
  | "resolved"
  | "postmortem_ready"
  | "skipped";

export type IncidentSummary = {
  id: string;
  title: string;
  status: IncidentStatus;
  grafana_incident_id: string | null;
  opened_at: string;
  resolved_at: string | null;
};

export type AgentEventRecord = {
  id: string;
  incident_id: string;
  agent_name: AgentName;
  event_type: AgentEventType;
  payload: Record<string, unknown>;
  created_at: string;
};

export type AgentTokenUsage = {
  agent_name: AgentName;
  input_tokens: number;
  output_tokens: number;
};

export type IncidentDetail = IncidentSummary & {
  events: AgentEventRecord[];
  token_usage: AgentTokenUsage[];
};

export type AgentStatusState = "idle" | "running" | "blocked";

export type AgentStatus = {
  name: AgentName;
  state: AgentStatusState;
  active_incidents: string[];
};

export type PostmortemReport = {
  summary_markdown: string;
  timeline: Record<string, unknown>[];
  generated_at: string;
};

export type AnalyticsSummary = {
  total_incidents: number;
  by_status: Record<string, number>;
  mttr_seconds: number | null;
  breaches_by_metric: Record<string, number>;
  breaches_by_region: Record<string, number>;
  total_input_tokens: number;
  total_output_tokens: number;
  estimated_cost_usd: number;
};

export type Role = "viewer" | "operator" | "admin";

export type AuthSession = {
  access_token: string;
  email: string;
  role: Role;
  workspace_id: string;
};

export type UserSummary = {
  id: string;
  email: string;
  role: Role;
  workspace_id: string;
  active: boolean;
  created_at: string;
};

export type AuditLogEntry = {
  id: string;
  actor_email: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  detail: Record<string, unknown>;
  created_at: string;
};

export type WorkspaceSummary = {
  id: string;
  name: string;
  created_at: string;
};
