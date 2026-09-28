"use client";

import { useEffect, useState } from "react";

import { useSession } from "@/components/session-provider";
import { loadProviderStatus, type ProviderStatus } from "@/lib/api/system";

export function ProviderStatusLoader() {
  const { session } = useSession();
  const [status, setStatus] = useState<ProviderStatus | null>(null);

  useEffect(() => {
    if (session == null) {
      return;
    }
    const timer = window.setTimeout(() => {
      void loadProviderStatus()
        .then(setStatus)
        .catch(() => setStatus(null));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [session]);

  if (session == null) {
    return null;
  }
  return <ProviderIndicator status={status} />;
}

export function ProviderIndicator({ status }: { status: ProviderStatus | null }) {
  if (status === null) {
    return null;
  }
  if (status.provider === "nvidia" && status.configured) {
    return <p className="mt-6 text-xs text-[var(--muted)]">Understanding is active</p>;
  }
  return null;
}
