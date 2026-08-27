"use client";

import type { IncidentSummary } from "@/lib/types";

const REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "apac", "sa-east-1"];
const SETTLED_STATUSES = new Set(["resolved", "postmortem_ready", "skipped"]);

// Region health is derived from the current incident list (already
// resolution-aware via REST refetch), not the raw event log -- an incident's
// original sentinel_alert event never goes away, so keying off it directly
// would leave a region stuck "degraded" forever after the incident resolves.
function regionHealth(region: string, incidents: IncidentSummary[]): "healthy" | "degraded" | "recovering" {
  const forRegion = incidents.filter((i) => i.title.includes(region));
  if (forRegion.some((i) => !SETTLED_STATUSES.has(i.status))) return "degraded";
  if (forRegion.some((i) => i.status === "postmortem_ready")) return "recovering";
  return "healthy";
}

const STATUS_STYLE: Record<string, string> = {
  healthy: "bg-emerald-500/10 border-emerald-500 text-emerald-700 dark:text-emerald-300",
  degraded: "bg-rose-500/10 border-rose-500 text-rose-700 dark:text-rose-300 animate-pulse",
  recovering: "bg-amber-500/10 border-amber-500 text-amber-700 dark:text-amber-300",
};

export function LiveQoEMap({ incidents }: { incidents: IncidentSummary[] }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-secondary">Live QoE map</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {REGIONS.map((region) => {
          const status = regionHealth(region, incidents);
          return (
            <div key={region} className={`rounded-md border px-3 py-4 text-center ${STATUS_STYLE[status]}`}>
              <p className="text-xs font-mono uppercase tracking-wide">{region}</p>
              <p className="mt-1 text-xs capitalize">{status}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
