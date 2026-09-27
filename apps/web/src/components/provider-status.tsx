"use client";

import { useEffect, useState } from "react";

import { loadProviderStatus, type ProviderStatus } from "@/lib/api/system";

export function ProviderStatusLoader() {
  const [status, setStatus] = useState<ProviderStatus | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadProviderStatus()
        .then(setStatus)
        .catch(() => setStatus(null));
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  return <ProviderIndicator status={status} />;
}

export function ProviderIndicator({ status }: { status: ProviderStatus | null }) {
  if (status === null) {
    return null;
  }
  if (status.provider === "nvidia" && status.configured) {
    return (
      <p className="mt-6 text-xs text-[var(--muted)]">
        <span className="tracking-[0.14em] uppercase">Understanding</span>
        <span className="mx-2" aria-hidden="true">
          ●
        </span>
        NVIDIA
      </p>
    );
  }
  if (status.provider === "nvidia") {
    return <p className="mt-6 text-xs text-[var(--muted)]">NVIDIA is not connected</p>;
  }
  return null;
}
