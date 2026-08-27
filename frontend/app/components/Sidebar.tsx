"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, Clapperboard, ClipboardList, LogIn, LogOut, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useWorkspace } from "@/lib/workspace";
import { ThemeToggle } from "./ThemeToggle";

const STORAGE_KEY = "premiere-control-room-sidebar-collapsed";

const NAV_ITEMS = [
  { href: "/", label: "Control Room", icon: Clapperboard },
  { href: "/history", label: "History & Analytics", icon: BarChart3 },
  { href: "/audit", label: "Audit Log", icon: ClipboardList },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { session, hydrated: authHydrated, setSession } = useAuth();
  const { workspaceId, setWorkspaceId, workspaces } = useWorkspace();
  const [collapsed, setCollapsed] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(STORAGE_KEY) === "1");
    } catch {
      // ignore
    } finally {
      setHydrated(true);
    }
  }, []);

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        // localStorage unavailable -- collapse state just won't persist.
      }
      return next;
    });
  };

  const signOut = () => {
    setSession(null);
    router.push("/");
  };

  return (
    <aside
      className={`sticky top-0 flex h-screen shrink-0 flex-col border-r border-line bg-surface transition-[width] duration-200 ${
        collapsed ? "w-[68px]" : "w-64"
      } ${hydrated ? "" : "invisible"}`}
    >
      <div className="flex h-16 shrink-0 items-center gap-2.5 border-b border-line px-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-brand/15 text-brand">
          <Clapperboard className="h-[18px] w-[18px]" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-primary">Premiere</p>
            <p className="truncate text-[11px] text-muted">Control Room</p>
          </div>
        )}
      </div>

      {!collapsed && workspaces.length > 0 && (
        <div className="border-b border-line px-3 py-3">
          <label className="mb-1 block text-[10px] font-medium uppercase tracking-wide text-muted">Workspace</label>
          <select
            value={workspaceId ?? ""}
            onChange={(e) => setWorkspaceId(e.target.value || null)}
            className="w-full rounded-md border border-line-strong bg-app px-2 py-1.5 text-xs text-primary"
          >
            <option value="">All workspaces</option>
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </div>
      )}

      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              title={collapsed ? label : undefined}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition ${
                active
                  ? "bg-brand/10 text-brand"
                  : "text-secondary hover:bg-surface-hover hover:text-primary"
              } ${collapsed ? "justify-center px-0" : ""}`}
            >
              <Icon className="h-[18px] w-[18px] shrink-0" />
              {!collapsed && <span className="truncate">{label}</span>}
            </Link>
          );
        })}
      </nav>

      <div className="space-y-2 border-t border-line p-3">
        {authHydrated && (
          <>
            {session ? (
              <div className={`rounded-md px-2.5 py-2 ${collapsed ? "text-center" : ""}`}>
                {!collapsed ? (
                  <>
                    <p className="truncate text-xs font-medium text-primary">{session.email}</p>
                    <p className="truncate text-[11px] uppercase tracking-wide text-muted">{session.role}</p>
                  </>
                ) : (
                  <p className="text-[10px] uppercase text-muted" title={session.email}>
                    {session.role.slice(0, 2)}
                  </p>
                )}
              </div>
            ) : null}
            <button
              type="button"
              onClick={session ? signOut : () => router.push("/login")}
              title={collapsed ? (session ? "Sign out" : "Sign in") : undefined}
              className={`flex w-full items-center gap-2 rounded-md border border-line px-2.5 py-2 text-xs font-medium text-secondary transition hover:border-line-strong hover:bg-surface-hover hover:text-primary ${
                collapsed ? "justify-center" : ""
              }`}
            >
              {session ? <LogOut className="h-4 w-4 shrink-0" /> : <LogIn className="h-4 w-4 shrink-0" />}
              {!collapsed && <span>{session ? "Sign out" : "Sign in"}</span>}
            </button>
          </>
        )}

        <ThemeToggle collapsed={collapsed} />
        <button
          type="button"
          onClick={toggleCollapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex w-full items-center justify-center gap-2 rounded-md px-2.5 py-2 text-xs font-medium text-muted transition hover:bg-surface-hover hover:text-primary"
        >
          {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
