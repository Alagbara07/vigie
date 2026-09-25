"use client";

import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { CommandCenter } from "@/components/command-center";
import { DashboardSkeleton, ErrorNotice, MissingBusiness } from "@/components/states";
import { recommendActions } from "@/lib/api/actions";
import { loadDemoBusiness } from "@/lib/api/businesses";
import { ApiError, MissingBusinessError } from "@/lib/api/client";
import { loadDashboardSummary, type DashboardSummary } from "@/lib/api/dashboard";
import { loadSignals, type SignalRecord } from "@/lib/api/signals";

type Ready = { phase: "ready"; summary: DashboardSummary; signals: SignalRecord[] };
type Phase = { phase: "loading" } | { phase: "error" } | { phase: "missing" } | Ready;

export function CommandCenterLoader() {
  const [state, setState] = useState<Phase>({ phase: "loading" });

  const load = useCallback(async () => {
    setState({ phase: "loading" });
    try {
      const business = await loadDemoBusiness();
      await recommendActions(business.id);
      const [summary, signals] = await Promise.all([
        loadDashboardSummary(business.id),
        loadSignals(business.id),
      ]);
      setState({ phase: "ready", summary, signals });
    } catch (error) {
      if (error instanceof MissingBusinessError) {
        setState({ phase: "missing" });
        return;
      }
      if (error instanceof ApiError || error instanceof Error) {
        setState({ phase: "error" });
      }
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <AppShell>
      {state.phase === "loading" ? <DashboardSkeleton /> : null}
      {state.phase === "error" ? <ErrorNotice onRetry={() => void load()} /> : null}
      {state.phase === "missing" ? <MissingBusiness /> : null}
      {state.phase === "ready" ? <CommandCenter summary={state.summary} signals={state.signals} /> : null}
    </AppShell>
  );
}
