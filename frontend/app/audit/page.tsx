"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AuditLogEntry } from "@/lib/types";

export default function AuditPage() {
  const { session, hydrated } = useAuth();
  const [entries, setEntries] = useState<AuditLogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!hydrated) return;
    if (!session) {
      setError("Sign in as an operator or admin to view the audit log.");
      return;
    }
    api
      .auditLog()
      .then(setEntries)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load the audit log."));
  }, [hydrated, session]);

  return (
    <div className="mx-auto min-h-screen max-w-7xl space-y-6 p-6 lg:p-8">
      <header className="border-b border-line pb-4">
        <h1 className="text-2xl font-semibold tracking-tight text-primary">Audit Log</h1>
        <p className="text-sm text-muted">Every sensitive action taken through the control room, who did it, and when</p>
      </header>

      {error && (
        <div className="rounded-lg border border-line bg-surface p-4 text-sm text-muted">
          {error}{" "}
          {!session && (
            <Link href="/login" className="text-brand hover:underline">
              Sign in
            </Link>
          )}
        </div>
      )}

      {!error && entries === null && <p className="text-sm text-muted">Loading…</p>}

      {entries && (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <th className="px-4 py-3 font-medium">When</th>
                <th className="px-4 py-3 font-medium">Actor</th>
                <th className="px-4 py-3 font-medium">Action</th>
                <th className="px-4 py-3 font-medium">Resource</th>
              </tr>
            </thead>
            <tbody>
              {entries.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-muted">
                    No audit entries yet.
                  </td>
                </tr>
              )}
              {entries.map((entry) => (
                <tr key={entry.id} className="border-b border-line last:border-0">
                  <td className="whitespace-nowrap px-4 py-3 text-muted">{new Date(entry.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-primary">{entry.actor_email}</td>
                  <td className="px-4 py-3">
                    <span className="rounded-full border border-line-strong px-2 py-0.5 text-xs uppercase text-secondary">
                      {entry.action.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted">
                    {entry.resource_type}
                    {entry.resource_id ? ` · ${entry.resource_id.slice(0, 8)}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
