"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { AuthSession, Role } from "./types";

const STORAGE_KEY = "premiere-control-room-session";
const ROLE_RANK: Record<Role, number> = { viewer: 0, operator: 1, admin: 2 };

function readStoredSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as AuthSession) : null;
  } catch {
    return null;
  }
}

type AuthContextValue = {
  session: AuthSession | null;
  hydrated: boolean;
  setSession: (session: AuthSession | null) => void;
  hasRole: (minimum: Role) => boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSessionState] = useState<AuthSession | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setSessionState(readStoredSession());
    setHydrated(true);
  }, []);

  const setSession = useCallback((next: AuthSession | null) => {
    setSessionState(next);
    try {
      if (next) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      else window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // localStorage unavailable -- session just won't persist across reloads.
    }
  }, []);

  const hasRole = useCallback(
    (minimum: Role) => session != null && ROLE_RANK[session.role] >= ROLE_RANK[minimum],
    [session],
  );

  const value = useMemo(() => ({ session, hydrated, setSession, hasRole }), [session, hydrated, setSession, hasRole]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}

// Read outside React (e.g. from lib/api.ts, which can't call hooks) -- kept
// in sync with the context's own storage writes above.
export function getStoredAccessToken(): string | null {
  return readStoredSession()?.access_token ?? null;
}
