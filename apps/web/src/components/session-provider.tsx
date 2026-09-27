"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { loadSession, type SessionState } from "@/lib/api/auth";

type SessionValue = {
  session: SessionState | null | undefined;
  refresh: () => Promise<SessionState | null>;
};

const SessionContext = createContext<SessionValue | null>(null);

const PUBLIC_PATHS = new Set(["/login", "/signup", "/demo", "/about"]);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionState | null | undefined>(undefined);

  const refresh = useCallback(async () => {
    try {
      const next = await loadSession();
      setSession(next);
      return next;
    } catch {
      setSession(null);
      return null;
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  const value = useMemo(() => ({ session, refresh }), [session, refresh]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error("Session is unavailable.");
  }
  return value;
}

export function SessionGate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { session } = useSession();
  const isPublic = PUBLIC_PATHS.has(pathname);

  useEffect(() => {
    if (isPublic || session === undefined) {
      return;
    }
    if (session === null) {
      router.replace("/login");
      return;
    }
    if (!session.current_business && pathname !== "/onboarding") {
      router.replace("/onboarding");
    }
  }, [isPublic, pathname, router, session]);

  if (isPublic) {
    return children;
  }
  if (session === undefined || session === null) {
    return <p className="sr-only">Checking your session</p>;
  }
  if (!session.current_business && pathname !== "/onboarding") {
    return <p className="sr-only">Create a business to continue</p>;
  }
  return children;
}
