"use client";

import Link from "next/link";
import { useState } from "react";

import type { ActionRecord } from "@/lib/api/actions";
import { ApiError } from "@/lib/api/client";
import { signalHref } from "@/lib/api/signals";
import { formatMoney } from "@/lib/format";
import { stateLabel, whyRecommendation } from "@/lib/product";

type ReviewPhase = "idle" | "pending" | "approved" | "rejected" | "error" | "decided";

export function ActionReview({
  action,
  onApprove,
  onReject,
  canDecide = true,
}: {
  action: ActionRecord;
  onApprove: () => Promise<void>;
  onReject: () => Promise<void>;
  canDecide?: boolean;
}) {
  const [phase, setPhase] = useState<ReviewPhase>(startingPhase(action.status));
  const amount =
    action.signal.financial_impact_amount && action.signal.currency
      ? formatMoney(action.signal.financial_impact_amount, action.signal.currency)
      : null;
  const status = visibleStatus(phase, action.status);

  async function decide(next: "approved" | "rejected", operation: () => Promise<void>) {
    setPhase("pending");
    try {
      await operation();
      setPhase(next);
    } catch (error) {
      setPhase(error instanceof ApiError && error.status === 409 ? "decided" : "error");
    }
  }

  return (
    <article className="max-w-2xl">
      <Link
        href={signalHref(action.signal_id, action.business_id)}
        className="text-sm text-[var(--muted)] underline-offset-4 hover:underline"
      >
        View evidence
      </Link>
      <p className="mt-6 text-xs font-semibold tracking-[0.14em] uppercase">{stateLabel(status)}</p>
      <h1 className="mt-2 font-[family-name:var(--font-newsreader)] text-4xl leading-tight font-medium">
        Review action
      </h1>
      <p className="mt-4 text-lg font-medium">VIGIE recommends. You decide.</p>
      <p className="mt-2 max-w-xl text-sm leading-6 text-[var(--muted)]">
        Approving this recommendation records your decision. No customer message will be sent automatically.
      </p>

      <section className="mt-8">
        <h2 className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">Why you&apos;re seeing this</h2>
        <p className="mt-3 max-w-xl text-base leading-7">
          {whyRecommendation({
            signal_type: action.signal.signal_type,
            financial_impact_amount: action.signal.financial_impact_amount,
            currency: action.signal.currency,
            description: action.description,
          })}
        </p>
      </section>

      <section className="mt-6 border-l-2 border-[var(--ink)] pl-4">
        <h2 className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">Signal</h2>
        <p className="mt-3 text-lg font-semibold">{action.signal.title}</p>
        {amount ? <p className="mt-1 text-sm font-semibold tabular-nums">{amount}</p> : null}
        <Link
          href={signalHref(action.signal_id, action.business_id)}
          className="mt-3 inline-block text-sm font-medium underline-offset-4 hover:underline"
        >
          Open the evidence
        </Link>
      </section>

      <section className="mt-6 border-t border-[var(--line)] pt-5">
        <h2 className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">Recommended action</h2>
        <p className="mt-3 text-base font-medium break-words">{action.title ?? "Review the recommendation"}</p>
        <h3 className="mt-5 text-xs tracking-[0.16em] text-[var(--muted)] uppercase">Suggested message</h3>
        <p className="mt-3 max-w-xl text-sm leading-6 break-words whitespace-pre-wrap">
          {action.proposed_content ?? "No customer message has been drafted. Review the signal and reply yourself."}
        </p>
      </section>

      {phase === "approved" ? (
        <div className="mt-8 border border-[var(--line)] bg-[var(--panel)] px-5 py-4" role="status">
          <p className="text-base font-semibold">Action approved.</p>
          <p className="mt-1 text-sm text-[var(--muted)]">No customer message was sent.</p>
        </div>
      ) : null}
      {phase === "rejected" ? (
        <p className="mt-8 text-base font-semibold" role="status">
          Recommendation rejected.
        </p>
      ) : null}
      {phase === "decided" ? (
        <p className="mt-8 text-sm text-[var(--muted)]" role="alert">
          This recommendation has already been decided.
        </p>
      ) : null}
      {phase === "error" ? (
        <section className="mt-8 max-w-lg border border-[var(--line)] bg-[var(--panel)] px-5 py-6" role="alert">
          <h2 className="text-xl font-semibold tracking-tight">VIGIE couldn&apos;t save this decision.</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">Try again.</p>
        </section>
      ) : null}

      {!canDecide && (phase === "idle" || phase === "pending" || phase === "error") ? (
        <p className="mt-8 text-sm text-[var(--muted)]">You do not have permission to approve actions for this business.</p>
      ) : null}
      {canDecide && (phase === "idle" || phase === "pending" || phase === "error") ? (
        <div className="mt-8 flex flex-wrap gap-3">
          <button
            type="button"
            disabled={phase === "pending"}
            onClick={() => void decide("approved", onApprove)}
            className="border border-[var(--ink)] bg-[var(--ink)] px-4 py-2 text-sm font-medium text-[var(--paper)] disabled:opacity-60"
          >
            Approve
          </button>
          <button
            type="button"
            disabled={phase === "pending"}
            onClick={() => void decide("rejected", onReject)}
            className="border border-[var(--ink)] px-4 py-2 text-sm font-medium disabled:opacity-60"
          >
            Reject
          </button>
        </div>
      ) : null}
    </article>
  );
}

function startingPhase(status: string): ReviewPhase {
  if (status === "APPROVED") {
    return "approved";
  }
  if (status === "REJECTED") {
    return "rejected";
  }
  return "idle";
}

function visibleStatus(phase: ReviewPhase, status: string): string {
  if (phase === "approved") {
    return "APPROVED";
  }
  if (phase === "rejected") {
    return "REJECTED";
  }
  return status;
}
