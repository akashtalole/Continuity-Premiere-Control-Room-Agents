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

export type IncidentDetail = IncidentSummary & {
  events: AgentEventRecord[];
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
};
