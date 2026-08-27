"use client";

import { Sidebar } from "./Sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-app text-primary">
      <Sidebar />
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}
