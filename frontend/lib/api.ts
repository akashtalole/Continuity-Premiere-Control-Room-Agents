import type { AgentStatus, AnalyticsSummary, IncidentDetail, IncidentSummary, PostmortemReport } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listIncidents: () => request<IncidentSummary[]>("/api/incidents"),
  getIncident: (id: string) => request<IncidentDetail>(`/api/incidents/${id}`),
  getPostmortem: (id: string) => request<PostmortemReport>(`/api/incidents/${id}/postmortem`),
  approve: (id: string) => request<{ status: string }>(`/api/incidents/${id}/approve`, { method: "POST" }),
  reject: (id: string) => request<{ status: string }>(`/api/incidents/${id}/reject`, { method: "POST" }),
  agentsStatus: () => request<AgentStatus[]>("/api/agents/status"),
  analyticsSummary: () => request<AnalyticsSummary>("/api/analytics/summary"),
  injectAnomaly: (body: {
    metric_name: string;
    observed_value: number;
    threshold: number;
    region: string;
  }) =>
    request<{ incident_id: string }>("/api/simulate/inject-anomaly", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export function wsUrl(): string {
  if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL;
  return `${API_BASE.replace(/^http/, "ws")}/ws/control-room`;
}
