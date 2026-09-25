import Link from "next/link";

import { actionHref } from "@/lib/api/actions";
import type { SignalDetail } from "@/lib/api/signals";
import { formatDate, formatMoney, severityLabel } from "@/lib/format";

export function SignalDetailView({ detail }: { detail: SignalDetail }) {
  const tone = severityLabel(detail.severity);
  return (
    <article className="max-w-2xl">
      <Link href="/" className="text-sm text-[var(--muted)] underline-offset-4 hover:underline">
        Back to command center
      </Link>
      <p className={`mt-6 text-[11px] font-semibold tracking-[0.14em] uppercase ${toneText(tone.tone)}`}>
        {tone.label}
      </p>
      <h1 className="mt-2 font-[family-name:var(--font-newsreader)] text-4xl leading-tight font-medium">
        {detail.title}
      </h1>
      <p className="mt-2 text-sm text-[var(--muted)]">{detail.status}</p>

      <section className="mt-8 border border-[var(--line)] bg-[var(--panel)] px-5 py-5">
        <h2 className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">What happened</h2>
        {detail.event ? (
          <p className="mt-3 text-sm">
            Detected event <span className="font-medium">{detail.event.event_type}</span>
          </p>
        ) : (
          <p className="mt-3 text-sm text-[var(--muted)]">No business event is attached.</p>
        )}
        {detail.commitment ? (
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-[var(--muted)]">Commitment</dt>
              <dd className="mt-1 font-medium">
                {detail.commitment.amount && detail.commitment.currency
                  ? formatMoney(detail.commitment.amount, detail.commitment.currency)
                  : detail.commitment.commitment_type}
              </dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Due</dt>
              <dd className="mt-1 font-medium">
                {detail.commitment.due_text ??
                  (detail.commitment.due_at ? formatDate(detail.commitment.due_at, detail.timezone) : "No date")}
              </dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Current state</dt>
              <dd className="mt-1 font-medium">{detail.commitment.status}</dd>
            </div>
          </dl>
        ) : null}
      </section>

      <section className="mt-6">
        <h2 className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">Why this matters</h2>
        <p className="mt-3 max-w-xl text-base leading-7">{detail.description}</p>
        {detail.financial_impact_amount && detail.currency ? (
          <p className="mt-3 text-sm">
            Revenue at risk{" "}
            <span className="font-semibold tabular-nums">
              {formatMoney(detail.financial_impact_amount, detail.currency)}
            </span>
          </p>
        ) : null}
      </section>

      <section className="mt-6">
        <h2 className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">Evidence</h2>
        {detail.evidence ? (
          <figure className="mt-3 border-l-2 border-[var(--ink)] pl-4">
            <figcaption className="text-xs tracking-[0.14em] text-[var(--muted)] uppercase">
              {detail.evidence.sender_type === "customer" ? "Based on customer message" : "Based on message"}
            </figcaption>
            <blockquote className="mt-2 text-base leading-7">&ldquo;{detail.evidence.content}&rdquo;</blockquote>
          </figure>
        ) : (
          <p className="mt-3 text-sm text-[var(--muted)]">No source message is attached to this signal.</p>
        )}
      </section>

      {detail.action ? (
        <section className="mt-6 border-t border-[var(--line)] pt-4">
          <h2 className="text-[11px] tracking-[0.14em] text-[var(--muted)] uppercase">Recommended action</h2>
          <p className="mt-2 max-w-xl text-sm leading-6 text-[var(--muted)]">
            {detail.action.description ?? "Review the signal before deciding."}
          </p>
          <p className="mt-2 text-sm font-medium">{detail.action.title ?? "Review the recommendation"}</p>
          <Link
            href={actionHref(detail.action.id, detail.business_id)}
            className="mt-3 inline-block text-sm font-medium underline-offset-4 hover:underline"
          >
            Review action
          </Link>
        </section>
      ) : null}

      {detail.customer ? (
        <section className="mt-6 border-t border-[var(--line)] pt-5">
          <h2 className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">Customer</h2>
          <p className="mt-3 text-base font-medium">{detail.customer.name}</p>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Customer since {formatDate(detail.customer.created_at, detail.timezone)}
          </p>
          {detail.conversation ? (
            <p className="mt-1 text-sm text-[var(--muted)]">
              {detail.conversation.message_count === 1
                ? "1 message"
                : `${detail.conversation.message_count} messages`}
            </p>
          ) : null}
        </section>
      ) : null}
    </article>
  );
}

function toneText(tone: "high" | "medium" | "low"): string {
  if (tone === "high") {
    return "text-[var(--high)]";
  }
  if (tone === "medium") {
    return "text-[var(--medium)]";
  }
  return "text-[var(--low)]";
}
