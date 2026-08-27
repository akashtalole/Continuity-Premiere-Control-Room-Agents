"use client";

import type { IncidentDetail } from "@/lib/types";

export function IncidentTimeline({ incident }: { incident: IncidentDetail | null }) {
  if (!incident) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">Incident timeline</h2>
        <p className="mt-3 text-sm text-slate-500">Select an incident to see its timeline.</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">Incident timeline</h2>
          <p className="mt-1 text-base font-medium text-slate-100">{incident.title}</p>
        </div>
        <span className="rounded-full border border-slate-700 px-2 py-1 text-xs uppercase text-slate-300">
          {incident.status.replace(/_/g, " ")}
        </span>
      </div>

      <ol className="mt-4 space-y-3 border-l border-slate-800 pl-4">
        {incident.events.map((event) => (
          <li key={event.id} className="relative">
            <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-sky-400" />
            <p className="text-sm text-slate-200">
              <span className="font-medium capitalize">{event.agent_name}</span>{" "}
              <span className="text-slate-400">&mdash; {event.event_type.replace(/_/g, " ")}</span>
            </p>
            <time className="text-xs text-slate-500">{new Date(event.created_at).toLocaleString()}</time>
          </li>
        ))}
        {incident.events.length === 0 && <p className="text-sm text-slate-500">No agent events recorded yet.</p>}
      </ol>
    </div>
  );
}
