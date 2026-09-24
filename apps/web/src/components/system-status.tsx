"use client";

import { useEffect, useState } from "react";

import { isHealthResponse, type HealthResponse } from "@/lib/health";

type StatusState =
  | { phase: "loading" }
  | { phase: "api_unavailable" }
  | { phase: "ready"; health: HealthResponse };

type Indicator = "loading" | "ok" | "down" | "unknown";

export function SystemStatus() {
  const [state, setState] = useState<StatusState>({ phase: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    async function loadStatus() {
      try {
        const response = await fetch("/api/health", {
          cache: "no-store",
          signal: controller.signal,
        });
        const payload: unknown = await response.json();
        if (!isHealthResponse(payload)) {
          setState({ phase: "api_unavailable" });
          return;
        }
        setState({ phase: "ready", health: payload });
      } catch {
        if (!controller.signal.aborted) {
          setState({ phase: "api_unavailable" });
        }
      }
    }

    void loadStatus();
    return () => controller.abort();
  }, []);

  const api = describeApi(state);
  const database = describeDatabase(state);

  return (
    <section className="mt-12 w-full max-w-md border border-zinc-200 bg-white p-6">
      <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">
        System status
      </h2>
      <ul className="mt-4 space-y-3">
        <StatusLine indicator={api.indicator} label={api.label} />
        <StatusLine indicator={database.indicator} label={database.label} />
      </ul>
    </section>
  );
}

function describeApi(state: StatusState): { indicator: Indicator; label: string } {
  if (state.phase === "loading") {
    return { indicator: "loading", label: "Checking API" };
  }
  if (state.phase === "api_unavailable") {
    return { indicator: "down", label: "API unavailable" };
  }
  return { indicator: "ok", label: "API Connected" };
}

function describeDatabase(state: StatusState): { indicator: Indicator; label: string } {
  if (state.phase === "loading") {
    return { indicator: "loading", label: "Checking database" };
  }
  if (state.phase === "api_unavailable") {
    return { indicator: "unknown", label: "Database status unknown" };
  }
  if (state.health.database === "ok") {
    return { indicator: "ok", label: "Database Ready" };
  }
  return { indicator: "down", label: "Database unavailable" };
}

function StatusLine({ indicator, label }: { indicator: Indicator; label: string }) {
  return (
    <li className="flex items-center gap-3 text-sm text-zinc-900">
      <span
        aria-hidden="true"
        className={`h-2.5 w-2.5 rounded-full ${indicatorClass(indicator)}`}
      />
      <span>{label}</span>
    </li>
  );
}

function indicatorClass(indicator: Indicator): string {
  if (indicator === "ok") {
    return "bg-emerald-600";
  }
  if (indicator === "down") {
    return "bg-red-600";
  }
  if (indicator === "unknown") {
    return "bg-zinc-400";
  }
  return "bg-amber-500";
}
