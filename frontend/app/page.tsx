"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, wsUrl } from "@/lib/api";
import { useControlRoomSocket } from "@/lib/useControlRoomSocket";
import type { AgentStatus, IncidentDetail, IncidentSummary } from "@/lib/types";
import { LiveQoEMap } from "./components/LiveQoEMap";
import { AgentActivityFeed } from "./components/AgentActivityFeed";
import { IncidentTimeline } from "./components/IncidentTimeline";
import { ApprovalModal, type PendingApproval } from "./components/ApprovalModal";
import { GrafanaPanelEmbed } from "./components/GrafanaPanelEmbed";

const RESOLVED_STATUSES = new Set(["resolved", "postmortem_ready", "skipped"]);

const MULTI_INCIDENT_SCENARIOS = [
  { metric_name: "rebuffer_ratio", observed_value: 0.19, threshold: 0.05, region: "us-east-1" },
  { metric_name: "origin_error_rate", observed_value: 0.09, threshold: 0.02, region: "eu-west-1" },
  { metric_name: "encoder_queue_depth", observed_value: 85, threshold: 50, region: "us-west-2" },
];

export default function ControlRoomPage() {
  const { events, status: socketStatus } = useControlRoomSocket(wsUrl());
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedIncident, setSelectedIncident] = useState<IncidentDetail | null>(null);
  const [agentStatuses, setAgentStatuses] = useState<AgentStatus[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<PendingApproval[]>([]);
  const [injecting, setInjecting] = useState(false);

  const refreshIncidents = async () => {
    const list = await api.listIncidents();
    setIncidents(list);
    if (!selectedId && list.length > 0) setSelectedId(list[0].id);
  };

  useEffect(() => {
    refreshIncidents().catch(() => undefined);
    const pollAgentStatus = () => api.agentsStatus().then(setAgentStatuses).catch(() => undefined);
    pollAgentStatus();
    const interval = setInterval(pollAgentStatus, 3000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-fetch the incident list + selected detail whenever a new agent event
  // lands, and surface a pending-approval modal when the Responder blocks.
  useEffect(() => {
    if (events.length === 0) return;
    const last = events[events.length - 1];
    refreshIncidents().catch(() => undefined);

    if (last.type === "responder_action_pending") {
      const entry: PendingApproval = {
        incidentId: last.incident_id,
        actionType: (last.payload.action_type as string) ?? "remediation",
        description:
          (last.payload.description as string) ??
          "The Responder wants to execute a high-risk remediation action.",
      };
      setPendingApprovals((prev) => (prev.some((p) => p.incidentId === entry.incidentId) ? prev : [...prev, entry]));
      setSelectedId((current) => current ?? last.incident_id);
    }
    if (last.incident_id === selectedId) {
      api.getIncident(last.incident_id).then(setSelectedIncident).catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events.length]);

  useEffect(() => {
    if (!selectedId) return;
    api.getIncident(selectedId).then(setSelectedIncident).catch(() => undefined);
  }, [selectedId]);

  const activeIncidentCount = useMemo(
    () => incidents.filter((i) => !RESOLVED_STATUSES.has(i.status)).length,
    [incidents],
  );

  const injectDemoAnomaly = async () => {
    setInjecting(true);
    try {
      const regions = ["us-east-1", "eu-west-1", "apac"];
      const region = regions[Math.floor(Math.random() * regions.length)];
      const { incident_id } = await api.injectAnomaly({
        metric_name: "rebuffer_ratio",
        observed_value: 0.18 + Math.random() * 0.1,
        threshold: 0.05,
        region,
      });
      setSelectedId(incident_id);
    } finally {
      setInjecting(false);
    }
  };

  // Fires three anomalies across different metrics/regions at once, to
  // demonstrate the orchestrator and UI handling overlapping in-flight
  // incidents (see docs/low-level-design.md's concurrent-incidents note).
  const injectConcurrentAnomalies = async () => {
    setInjecting(true);
    try {
      await Promise.all(MULTI_INCIDENT_SCENARIOS.map((scenario) => api.injectAnomaly(scenario)));
    } finally {
      setInjecting(false);
    }
  };

  return (
    <main className="mx-auto min-h-screen max-w-7xl space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Premiere Control Room</h1>
          <p className="text-sm text-slate-400">Agentic reliability engineer for live media premieres</p>
        </div>
        <div className="flex items-center gap-4">
          <span
            className={`flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
              socketStatus === "open"
                ? "border-emerald-600 text-emerald-300"
                : "border-amber-600 text-amber-300"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${socketStatus === "open" ? "bg-emerald-400" : "bg-amber-400 animate-pulse"}`}
            />
            {socketStatus === "open" ? "live" : socketStatus}
          </span>
          <span className="text-xs text-slate-400">{activeIncidentCount} active incident(s)</span>
          <Link
            href="/history"
            className="rounded-md border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800"
          >
            History &amp; analytics
          </Link>
          <button
            type="button"
            onClick={injectConcurrentAnomalies}
            disabled={injecting}
            className="rounded-md border border-rose-600 px-3 py-1.5 text-xs font-medium text-rose-300 hover:bg-rose-600/10 disabled:opacity-50"
          >
            {injecting ? "Injecting…" : "Inject 3 concurrent anomalies"}
          </button>
          <button
            type="button"
            onClick={injectDemoAnomaly}
            disabled={injecting}
            className="rounded-md bg-rose-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-rose-500 disabled:opacity-50"
          >
            {injecting ? "Injecting…" : "Inject demo anomaly"}
          </button>
        </div>
      </header>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-5">
        {agentStatuses.map((agent) => (
          <div
            key={agent.name}
            className={`rounded-md border px-3 py-2 text-center text-xs ${
              agent.state === "blocked"
                ? "border-amber-500 text-amber-300"
                : agent.state === "running"
                  ? "border-sky-500 text-sky-300"
                  : "border-slate-800 text-slate-500"
            }`}
          >
            <p className="font-medium capitalize">{agent.name}</p>
            <p className="capitalize">
              {agent.state}
              {agent.active_incidents.length > 1 ? ` ×${agent.active_incidents.length}` : ""}
            </p>
          </div>
        ))}
      </section>

      <LiveQoEMap incidents={incidents} />

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <AgentActivityFeed events={events} />
        </div>
        <div className="space-y-6 lg:col-span-2">
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-300">Incidents</h2>
            <div className="space-y-2">
              {incidents.length === 0 && <p className="text-sm text-slate-500">No incidents yet.</p>}
              {incidents.map((incident) => (
                <button
                  key={incident.id}
                  type="button"
                  onClick={() => setSelectedId(incident.id)}
                  className={`flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm ${
                    incident.id === selectedId
                      ? "border-sky-500 bg-sky-500/10"
                      : "border-slate-800 hover:border-slate-700"
                  }`}
                >
                  <span className="truncate">{incident.title}</span>
                  <span className="ml-2 shrink-0 text-xs uppercase text-slate-400">
                    {incident.status.replace(/_/g, " ")}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <IncidentTimeline incident={selectedIncident} />

          <GrafanaPanelEmbed dashboardUid="premiere-slo-overview" panelId={1} />
        </div>
      </section>

      <ApprovalModal
        queue={pendingApprovals}
        onResolved={(incidentId) => {
          setPendingApprovals((prev) => prev.filter((p) => p.incidentId !== incidentId));
        }}
      />
    </main>
  );
}
