"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

import { ActionReview } from "@/components/action-review";
import { AppShell } from "@/components/app-shell";
import { DetailSkeleton, ErrorNotice } from "@/components/states";
import { canApprove } from "@/lib/access";
import { approveAction, loadAction, rejectAction, type ActionRecord } from "@/lib/api/actions";
import { loadSession } from "@/lib/api/auth";

export function ActionReviewLoader() {
  const params = useParams<{ actionId: string }>();
  const searchParams = useSearchParams();
  const businessId = searchParams.get("business_id");
  const actionId = params.actionId;
  const [state, setState] = useState<
    { phase: "loading" } | { phase: "error" } | { phase: "ready"; action: ActionRecord; canDecide: boolean }
  >({ phase: "loading" });

  const load = useCallback(async () => {
    if (!businessId || !actionId) {
      setState({ phase: "error" });
      return;
    }
    setState({ phase: "loading" });
    try {
      const [action, session] = await Promise.all([loadAction(actionId, businessId), loadSession()]);
      const membership = session.businesses.find((business) => business.id === businessId);
      setState({ phase: "ready", action, canDecide: canApprove(membership?.role) });
    } catch {
      setState({ phase: "error" });
    }
  }, [actionId, businessId]);

  useEffect(() => {
    document.title = "Review · VIGIE";
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <AppShell>
      {state.phase === "loading" ? <DetailSkeleton label="Opening this recommendation" /> : null}
      {state.phase === "error" ? (
        <ErrorNotice
          onRetry={() => void load()}
          title="VIGIE couldn't open this recommendation."
          detail="Try again."
        />
      ) : null}
      {state.phase === "ready" ? (
        <ActionReview
          action={state.action}
          canDecide={state.canDecide}
          onApprove={async () => {
            await approveAction(state.action.id, state.action.business_id);
          }}
          onReject={async () => {
            await rejectAction(state.action.id, state.action.business_id);
          }}
        />
      ) : null}
    </AppShell>
  );
}
