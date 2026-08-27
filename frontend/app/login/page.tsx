"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { setSession } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = await api.auth.login(email, password);
      setSession(session);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Invalid email or password." : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <form onSubmit={onSubmit} className="w-full max-w-sm rounded-lg border border-line bg-surface p-6">
        <div className="mb-6 flex items-center gap-2">
          <LogIn className="h-5 w-5 text-brand" />
          <h1 className="text-lg font-semibold text-primary">Sign in</h1>
        </div>
        <p className="mb-6 text-sm text-muted">
          Read-only views don&apos;t require signing in. Approving remediations, injecting demo incidents, and the
          audit log do.
        </p>

        <label className="mb-3 block text-xs font-medium uppercase tracking-wide text-muted">
          Email
          <input
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-md border border-line-strong bg-app px-3 py-2 text-sm text-primary"
          />
        </label>

        <label className="mb-4 block text-xs font-medium uppercase tracking-wide text-muted">
          Password
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-line-strong bg-app px-3 py-2 text-sm text-primary"
          />
        </label>

        {error && <p className="mb-4 text-sm text-rose-600 dark:text-rose-400">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
