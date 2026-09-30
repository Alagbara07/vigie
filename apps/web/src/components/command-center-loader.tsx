"use client";

import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { CommandCenter } from "@/components/command-center";
import { DashboardSkeleton, ErrorNotice, MissingBusiness } from "@/components/states";
import { recommendActions } from "@/lib/api/actions";
import { loadSession, type MembershipBusiness } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { loadDashboardSummary, type DashboardSummary } from "@/lib/api/dashboard";
import { loadSignals, type SignalRecord } from "@/lib/api/signals";

type Ready = {
  phase: "ready";
  summary: DashboardSummary;
  signals: SignalRecord[];
  dashboardError: boolean;
};
type Phase = { phase: "loading" } | { phase: "signals-error" } | { phase: "missing" } | Ready;

export function summaryFromSignals(business: MembershipBusiness, signals: SignalRecord[]): DashboardSummary {
  const open = signals.filter((signal) => signal.status === "OPEN");
  return {
    business_id: business.id,
    business_name: business.name,
    timezone: business.timezone,
    currency: business.default_currency,
    open_signals: open.length,
    high_priority_signals: open.filter((signal) => signal.severity === "HIGH" || signal.severity === "CRITICAL").length,
    revenue_at_risk: "0",
    missed_commitments: open.filter((signal) => signal.signal_type === "OVERDUE_PAYMENT").length,
    opportunity_signals: open.filter((signal) => signal.attention_group === "opportunity").length,
    recent_conversations: [],
  };
}

export function CommandCenterLoader() {
  const [state, setState] = useState<Phase>({ phase: "loading" });

  const load = useCallback(async () => {
    setState({ phase: "loading" });
    try {
      const session = await loadSession();
      const business = session.current_business;
      if (!business) {
        setState({ phase: "missing" });
        return;
      }
      try {
        await recommendActions(business.id);
      } catch {
        // Recommendations are derived from signals. A failure here must not hide the feed.
      }
      let signals: SignalRecord[];
      try {
        signals = await loadSignals(business.id);
      } catch {
        setState({ phase: "signals-error" });
        return;
      }
      try {
        const summary = await loadDashboardSummary(business.id);
        setState({ phase: "ready", summary, signals, dashboardError: false });
      } catch {
        setState({
          phase: "ready",
          summary: summaryFromSignals(business, signals),
          signals,
          dashboardError: true,
        });
      }
    } catch (error) {
      if (error instanceof ApiError || error instanceof Error) {
        setState({ phase: "signals-error" });
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
      {state.phase === "signals-error" ? <ErrorNotice onRetry={() => void load()} /> : null}
      {state.phase === "missing" ? <MissingBusiness /> : null}
      {state.phase === "ready" ? (
        <>
          {state.dashboardError ? (
            <ErrorNotice
              onRetry={() => void load()}
              title="VIGIE couldn't load the dashboard summary."
              detail="Signals are still shown below."
            />
          ) : null}
          <CommandCenter summary={state.summary} signals={state.signals} />
        </>
      ) : null}
    </AppShell>
  );
}
