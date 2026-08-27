"use client";

import { Download } from "lucide-react";
import { api } from "@/lib/api";
import type { IncidentDetail } from "@/lib/types";

export function IncidentTimeline({ incident }: { incident: IncidentDetail | null }) {
  if (!incident) {
    return (
      <div className="rounded-lg border border-line bg-surface p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-secondary">Incident timeline</h2>
        <p className="mt-3 text-sm text-muted">Select an incident to see its timeline.</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-secondary">Incident timeline</h2>
          <p className="mt-1 text-base font-medium text-primary">{incident.title}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {incident.status === "postmortem_ready" && (
            <a
              href={api.postmortemExportUrl(incident.id)}
              download
              className="flex items-center gap-1 rounded-md border border-line-strong px-2 py-1 text-xs text-secondary hover:bg-surface-hover"
            >
              <Download className="h-3.5 w-3.5" /> Postmortem
            </a>
          )}
          <span className="rounded-full border border-line-strong px-2 py-1 text-xs uppercase text-secondary">
            {incident.status.replace(/_/g, " ")}
          </span>
        </div>
      </div>

      {incident.token_usage.length > 0 && (
        <p className="mt-3 text-xs text-muted">
          Gemini usage:{" "}
          {incident.token_usage.reduce((sum, u) => sum + u.input_tokens + u.output_tokens, 0).toLocaleString()} tokens
          across {incident.token_usage.length} agent turn(s)
        </p>
      )}

      <ol className="mt-4 space-y-3 border-l border-line pl-4">
        {incident.events.map((event) => {
          const confidence = event.payload.confidence;
          return (
            <li key={event.id} className="relative">
              <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-sky-400" />
              <p className="text-sm text-secondary">
                <span className="font-medium capitalize text-primary">{event.agent_name}</span>{" "}
                <span className="text-muted">&mdash; {event.event_type.replace(/_/g, " ")}</span>
                {typeof confidence === "number" && (
                  <span className="ml-2 rounded-full border border-line-strong px-1.5 py-0.5 text-[10px] text-muted">
                    {Math.round(confidence * 100)}% confidence
                  </span>
                )}
              </p>
              <time className="text-xs text-muted">{new Date(event.created_at).toLocaleString()}</time>
            </li>
          );
        })}
        {incident.events.length === 0 && <p className="text-sm text-muted">No agent events recorded yet.</p>}
      </ol>
    </div>
  );
}
