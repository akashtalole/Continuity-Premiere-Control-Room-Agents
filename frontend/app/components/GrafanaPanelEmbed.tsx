"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function GrafanaPanelEmbed({
  dashboardUid,
  panelId,
  deepLink,
}: {
  dashboardUid: string;
  panelId: number;
  deepLink?: string;
}) {
  const src = `${API_BASE}/api/dashboards/panel-image?dashboard_uid=${encodeURIComponent(dashboardUid)}&panel_id=${panelId}`;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">Grafana panel</h2>
        {deepLink && (
          <a href={deepLink} target="_blank" rel="noreferrer" className="text-xs text-sky-400 hover:underline">
            Open in Grafana &rarr;
          </a>
        )}
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={`Grafana panel ${panelId} on dashboard ${dashboardUid}`}
        className="mt-3 w-full rounded-md border border-slate-800 bg-slate-950"
        onError={(e) => {
          (e.target as HTMLImageElement).style.display = "none";
        }}
      />
    </div>
  );
}
