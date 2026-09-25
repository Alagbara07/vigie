"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

import { ActionReview } from "@/components/action-review";
import { AppShell } from "@/components/app-shell";
import { DetailSkeleton, ErrorNotice } from "@/components/states";
import { approveAction, loadAction, rejectAction, type ActionRecord } from "@/lib/api/actions";

export function ActionReviewLoader() {
  const params = useParams<{ actionId: string }>();
  const searchParams = useSearchParams();
  const businessId = searchParams.get("business_id");
  const actionId = params.actionId;
  const [state, setState] = useState<
    { phase: "loading" } | { phase: "error" } | { phase: "ready"; action: ActionRecord }
  >({ phase: "loading" });

  const load = useCallback(async () => {
    if (!businessId || !actionId) {
      setState({ phase: "error" });
      return;
    }
    setState({ phase: "loading" });
    try {
      const action = await loadAction(actionId, businessId);
      setState({ phase: "ready", action });
    } catch {
      setState({ phase: "error" });
    }
  }, [actionId, businessId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <AppShell>
      {state.phase === "loading" ? <DetailSkeleton /> : null}
      {state.phase === "error" ? <ErrorNotice onRetry={() => void load()} /> : null}
      {state.phase === "ready" ? (
        <ActionReview
          action={state.action}
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
