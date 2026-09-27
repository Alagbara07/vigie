"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { SignalDetailView } from "@/components/signal-detail";
import { DetailSkeleton, ErrorNotice } from "@/components/states";
import { recommendActions } from "@/lib/api/actions";
import { loadSignalDetail, type SignalDetail } from "@/lib/api/signals";

export function SignalDetailLoader() {
  const params = useParams<{ signalId: string }>();
  const searchParams = useSearchParams();
  const businessId = searchParams.get("business_id");
  const signalId = params.signalId;
  const [state, setState] = useState<{ phase: "loading" } | { phase: "error" } | { phase: "ready"; detail: SignalDetail }>(
    { phase: "loading" },
  );

  const load = useCallback(async () => {
    if (!businessId || !signalId) {
      setState({ phase: "error" });
      return;
    }
    setState({ phase: "loading" });
    try {
      await recommendActions(businessId, signalId);
      const detail = await loadSignalDetail(signalId, businessId);
      setState({ phase: "ready", detail });
    } catch {
      setState({ phase: "error" });
    }
  }, [businessId, signalId]);

  useEffect(() => {
    document.title = "Signal · VIGIE";
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <AppShell>
      {state.phase === "loading" ? <DetailSkeleton /> : null}
      {state.phase === "error" ? <ErrorNotice onRetry={() => void load()} /> : null}
      {state.phase === "ready" ? <SignalDetailView detail={state.detail} /> : null}
    </AppShell>
  );
}
