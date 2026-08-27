"use client";

import type { AgentEvent, AgentName } from "@/lib/types";

const AGENT_META: Record<AgentName, { label: string; color: string; icon: string }> = {
  sentinel: { label: "Sentinel", color: "border-amber-400 text-amber-300", icon: "\u{1F6E1}" },
  detective: { label: "Detective", color: "border-orange-400 text-orange-300", icon: "\u{1F50D}" },
  producer: { label: "Producer", color: "border-sky-400 text-sky-300", icon: "\u{1F4C4}" },
  responder: { label: "Responder", color: "border-emerald-400 text-emerald-300", icon: "\u{1F527}" },
  wrap: { label: "Wrap", color: "border-violet-400 text-violet-300", icon: "\u{1F4DD}" },
};

const EVENT_LABEL: Record<string, string> = {
  sentinel_alert: "flagged an SLO breach",
  detective_finding: "correlated a root cause",
  producer_brief: "opened an incident brief",
  responder_action_pending: "is requesting approval",
  responder_action_executed: "executed a remediation",
  incident_resolved: "resolved the incident",
  postmortem_ready: "published the postmortem",
};

export function AgentActivityFeed({ events }: { events: AgentEvent[] }) {
  const ordered = [...events].reverse();

  return (
    <div className="flex h-full flex-col rounded-lg border border-slate-800 bg-slate-900/60">
      <div className="border-b border-slate-800 px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">Agent activity feed</h2>
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {ordered.length === 0 && <p className="p-4 text-sm text-slate-500">No agent activity yet. Monitoring live SLOs&hellip;</p>}
        {ordered.map((event, idx) => {
          const meta = AGENT_META[event.agent];
          return (
            <div
              key={`${event.incident_id}-${event.timestamp}-${idx}`}
              className={`rounded-md border-l-2 bg-slate-800/50 px-3 py-2 text-sm ${meta.color}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">
                  {meta.icon} {meta.label} {EVENT_LABEL[event.type] ?? event.type}
                </span>
                <time className="shrink-0 text-xs text-slate-500">
                  {new Date(event.timestamp).toLocaleTimeString()}
                </time>
              </div>
              <p className="mt-1 truncate text-xs text-slate-400">incident {event.incident_id.slice(0, 8)}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
