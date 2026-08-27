import { getStoredAccessToken } from "./auth";
import type {
  AgentStatus,
  AnalyticsSummary,
  AuditLogEntry,
  AuthSession,
  IncidentDetail,
  IncidentSummary,
  PostmortemReport,
  UserSummary,
  WorkspaceSummary,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getStoredAccessToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const status = res.status;
    const message =
      status === 401
        ? "Sign in to do that."
        : status === 403
          ? "You don't have permission to do that."
          : `${init?.method ?? "GET"} ${path} failed: ${status}`;
    throw new ApiError(status, message);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listIncidents: (workspaceId?: string | null) =>
    request<IncidentSummary[]>(`/api/incidents${workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : ""}`),
  getIncident: (id: string) => request<IncidentDetail>(`/api/incidents/${id}`),
  getPostmortem: (id: string) => request<PostmortemReport>(`/api/incidents/${id}/postmortem`),
  postmortemExportUrl: (id: string) => `${API_BASE}/api/incidents/${id}/postmortem/export`,
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
  auditLog: () => request<AuditLogEntry[]>("/api/audit-log"),
  workspaces: {
    list: () => request<WorkspaceSummary[]>("/api/workspaces"),
    create: (body: { id: string; name: string }) =>
      request<WorkspaceSummary>("/api/workspaces", { method: "POST", body: JSON.stringify(body) }),
  },
  auth: {
    login: (email: string, password: string) =>
      request<AuthSession>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
    me: () => request<UserSummary>("/api/auth/me"),
    listUsers: () => request<UserSummary[]>("/api/auth/users"),
    createUser: (body: { email: string; password: string; role: string; workspace_id?: string }) =>
      request<UserSummary>("/api/auth/users", { method: "POST", body: JSON.stringify(body) }),
    revokeUser: (id: string) => request<UserSummary>(`/api/auth/users/${id}/revoke`, { method: "POST" }),
  },
};

export function wsUrl(): string {
  if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL;
  return `${API_BASE.replace(/^http/, "ws")}/ws/control-room`;
}
