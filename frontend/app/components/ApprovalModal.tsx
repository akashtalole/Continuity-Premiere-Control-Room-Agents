"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export type PendingApproval = {
  incidentId: string;
  actionType: string;
  description: string;
};

export function ApprovalModal({
  queue,
  onResolved,
}: {
  queue: PendingApproval[];
  onResolved: (incidentId: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const pending = queue[0] ?? null;

  if (!pending) return null;

  const act = async (decision: "approve" | "reject") => {
    setBusy(true);
    try {
      if (decision === "approve") await api.approve(pending.incidentId);
      else await api.reject(pending.incidentId);
      onResolved(pending.incidentId);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-md rounded-lg border border-amber-500/50 bg-slate-900 p-6 shadow-xl">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-400">Human approval required</p>
          {queue.length > 1 && (
            <span className="rounded-full border border-amber-500/50 px-2 py-0.5 text-xs text-amber-300">
              1 of {queue.length} pending
            </span>
          )}
        </div>
        <h3 className="mt-2 text-lg font-semibold text-slate-100">Responder wants to take a high-risk action</h3>
        <p className="mt-2 text-xs font-mono uppercase tracking-wide text-slate-500">{pending.actionType}</p>
        <p className="mt-1 text-sm text-slate-300">{pending.description}</p>
        <p className="mt-2 text-xs text-slate-500">Incident {pending.incidentId.slice(0, 8)}</p>

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            disabled={busy}
            onClick={() => act("reject")}
            className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            Reject
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => act("approve")}
            className="rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-emerald-400 disabled:opacity-50"
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}
