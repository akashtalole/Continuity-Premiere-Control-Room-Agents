"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { WorkspaceSummary } from "./types";

const STORAGE_KEY = "premiere-control-room-workspace";

type WorkspaceContextValue = {
  workspaceId: string | null; // null = all workspaces
  setWorkspaceId: (id: string | null) => void;
  workspaces: WorkspaceSummary[];
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [workspaceId, setWorkspaceIdState] = useState<string | null>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) setWorkspaceIdState(stored);
    } catch {
      // ignore
    }
    api.workspaces
      .list()
      .then(setWorkspaces)
      .catch(() => undefined);
  }, []);

  const setWorkspaceId = useCallback((id: string | null) => {
    setWorkspaceIdState(id);
    try {
      if (id) window.localStorage.setItem(STORAGE_KEY, id);
      else window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // localStorage unavailable -- selection just won't persist.
    }
  }, []);

  const value = useMemo(() => ({ workspaceId, setWorkspaceId, workspaces }), [workspaceId, setWorkspaceId, workspaces]);

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within a WorkspaceProvider");
  return ctx;
}
