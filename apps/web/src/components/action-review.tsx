"use client";

import Link from "next/link";
import { useState } from "react";

import type { ActionRecord } from "@/lib/api/actions";
import { ApiError } from "@/lib/api/client";
import { signalHref } from "@/lib/api/signals";
import { formatMoney } from "@/lib/format";

type ReviewPhase = "idle" | "pending" | "approved" | "rejected" | "error" | "decided";

export function ActionReview({
  action,
  onApprove,
  onReject,
}: {
  action: ActionRecord;
  onApprove: () => Promise<void>;
  onReject: () => Promise<void>;
}) {
  const [phase, setPhase] = useState<ReviewPhase>(startingPhase(action.status));
  const amount =
    action.signal.financial_impact_amount && action.signal.currency
      ? formatMoney(action.signal.financial_impact_amount, action.signal.currency)
      : null;

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
        Back to signal
      </Link>
      <h1 className="mt-6 font-[family-name:var(--font-newsreader)] text-4xl leading-tight font-medium">
        Review action
      </h1>

      <section className="mt-8">
        <h2 className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">Why this action was recommended</h2>
        <p className="mt-3 max-w-xl text-base leading-7">
          {action.description ?? "Recommended from the signal already on this record."}
        </p>
      </section>

      <section className="mt-6 border-l-2 border-[var(--ink)] pl-4">
        <h2 className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">Signal</h2>
        <p className="mt-3 text-lg font-semibold">{action.signal.title}</p>
        {amount ? <p className="mt-1 text-sm font-semibold tabular-nums">{amount}</p> : null}
      </section>

      <section className="mt-6 border-t border-[var(--line)] pt-5">
        <h2 className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">Proposed action</h2>
        <p className="mt-3 text-base font-medium">{action.title ?? "Review the recommendation"}</p>
        <h3 className="mt-5 text-xs tracking-[0.16em] text-[var(--muted)] uppercase">Draft</h3>
        <p className="mt-3 max-w-xl text-sm leading-6 break-words whitespace-pre-wrap">
          {action.proposed_content ?? "No customer message has been drafted. Review the signal and reply yourself."}
        </p>
      </section>

      {phase === "approved" ? (
        <div className="mt-8 border border-[var(--line)] bg-[var(--panel)] px-5 py-4" role="status">
          <p className="text-base font-semibold">Action approved.</p>
          <p className="mt-1 text-sm text-[var(--muted)]">No message has been sent.</p>
        </div>
      ) : null}
      {phase === "rejected" ? (
        <p className="mt-8 text-base font-semibold" role="status">
          Action rejected.
        </p>
      ) : null}
      {phase === "decided" ? (
        <p className="mt-8 text-sm text-[var(--muted)]" role="alert">
          This recommendation has already been decided.
        </p>
      ) : null}
      {phase === "error" ? (
        <section className="mt-8 max-w-lg border border-[var(--line)] bg-[var(--panel)] px-5 py-6" role="alert">
          <h2 className="text-xl font-semibold tracking-tight">VIGIE can&apos;t reach the intelligence service.</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">Check that the API is running and try again.</p>
        </section>
      ) : null}

      {phase === "idle" || phase === "pending" || phase === "error" ? (
        <div className="mt-8 flex gap-3">
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
