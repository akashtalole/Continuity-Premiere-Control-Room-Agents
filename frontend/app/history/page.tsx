"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { AnalyticsSummary, IncidentSummary, PostmortemReport } from "@/lib/types";

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}

function BreachBars({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, count]) => count));

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-300">{title}</h2>
      {entries.length === 0 && <p className="text-sm text-slate-500">No data yet.</p>}
      <div className="space-y-2">
        {entries.map(([label, count]) => (
          <div key={label} className="flex items-center gap-3 text-xs">
            <span className="w-32 shrink-0 truncate font-mono text-slate-400">{label}</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-800">
              <div className="h-full rounded-full bg-sky-500" style={{ width: `${(count / max) * 100}%` }} />
            </div>
            <span className="w-6 shrink-0 text-right text-slate-300">{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4 text-center">
      <p className="text-2xl font-semibold text-slate-100">{value}</p>
      <p className="mt-1 text-xs uppercase tracking-wide text-slate-400">{label}</p>
    </div>
  );
}

export default function HistoryPage() {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [postmortems, setPostmortems] = useState<Record<string, PostmortemReport | "unavailable">>({});

  useEffect(() => {
    api.listIncidents().then(setIncidents).catch(() => undefined);
    api.analyticsSummary().then(setAnalytics).catch(() => undefined);
  }, []);

  const statuses = useMemo(() => Array.from(new Set(incidents.map((i) => i.status))).sort(), [incidents]);

  const filtered = useMemo(
    () =>
      incidents.filter((i) => {
        if (statusFilter !== "all" && i.status !== statusFilter) return false;
        if (query.trim() && !i.title.toLowerCase().includes(query.trim().toLowerCase())) return false;
        return true;
      }),
    [incidents, statusFilter, query],
  );

  const toggleExpanded = async (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    if (!postmortems[id]) {
      try {
        const pm = await api.getPostmortem(id);
        setPostmortems((prev) => ({ ...prev, [id]: pm }));
      } catch {
        setPostmortems((prev) => ({ ...prev, [id]: "unavailable" }));
      }
    }
  };

  return (
    <main className="mx-auto min-h-screen max-w-7xl space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Incident History &amp; Analytics</h1>
          <p className="text-sm text-slate-400">Every incident the crew has ever handled, with cross-incident stats</p>
        </div>
        <Link
          href="/"
          className="rounded-md border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800"
        >
          &larr; Back to control room
        </Link>
      </header>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Total incidents" value={analytics?.total_incidents ?? "—"} />
        <StatTile label="MTTR" value={formatDuration(analytics?.mttr_seconds ?? null)} />
        <StatTile label="Resolved" value={analytics?.by_status.postmortem_ready ?? 0} />
        <StatTile
          label="Active"
          value={
            analytics
              ? analytics.total_incidents -
                (analytics.by_status.postmortem_ready ?? 0) -
                (analytics.by_status.resolved ?? 0) -
                (analytics.by_status.skipped ?? 0)
              : "—"
          }
        />
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <BreachBars title="Breaches by metric" counts={analytics?.breaches_by_metric ?? {}} />
        <BreachBars title="Breaches by region" counts={analytics?.breaches_by_region ?? {}} />
      </section>

      <section className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">Incidents</h2>
          <input
            type="text"
            placeholder="Search by title…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="ml-auto rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 placeholder:text-slate-500"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
          >
            <option value="all">All statuses</option>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          {filtered.length === 0 && <p className="text-sm text-slate-500">No incidents match.</p>}
          {filtered.map((incident) => {
            const pm = postmortems[incident.id];
            return (
              <div key={incident.id} className="rounded-md border border-slate-800">
                <button
                  type="button"
                  onClick={() => toggleExpanded(incident.id)}
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-800/50"
                >
                  <span className="truncate">{incident.title}</span>
                  <span className="ml-2 flex shrink-0 items-center gap-3 text-xs text-slate-400">
                    <span className="uppercase">{incident.status.replace(/_/g, " ")}</span>
                    <span>{new Date(incident.opened_at).toLocaleString()}</span>
                  </span>
                </button>
                {expandedId === incident.id && (
                  <div className="border-t border-slate-800 px-3 py-3 text-sm">
                    {!pm && <p className="text-slate-500">Loading postmortem…</p>}
                    {pm === "unavailable" && (
                      <p className="text-slate-500">No postmortem generated for this incident yet.</p>
                    )}
                    {pm && pm !== "unavailable" && (
                      <pre className="whitespace-pre-wrap font-sans text-slate-300">{pm.summary_markdown}</pre>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>
    </main>
  );
}
