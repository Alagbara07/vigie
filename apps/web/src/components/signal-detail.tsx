import Link from "next/link";

import { actionHref } from "@/lib/api/actions";
import type { SignalDetail } from "@/lib/api/signals";
import { formatDate, formatMoney, severityLabel } from "@/lib/format";
import { detectedAs, reachedSteps, stateLabel, whyItMatters } from "@/lib/product";

export function SignalDetailView({ detail }: { detail: SignalDetail }) {
  const tone = severityLabel(detail.severity);
  const amount =
    detail.commitment?.amount && detail.commitment.currency
      ? formatMoney(detail.commitment.amount, detail.commitment.currency)
      : detail.financial_impact_amount && detail.currency
        ? formatMoney(detail.financial_impact_amount, detail.currency)
        : null;
  const due =
    detail.commitment?.due_text ??
    (detail.commitment?.due_at ? formatDate(detail.commitment.due_at, detail.timezone) : null);

  return (
    <article className="max-w-2xl">
      <Link href="/" className="text-sm text-[var(--muted)] underline-offset-4 hover:underline">
        Back to command center
      </Link>
      <p className={`mt-6 text-[11px] font-semibold tracking-[0.14em] uppercase ${toneText(tone.tone)}`}>
        {tone.label}
        <span className="text-[var(--muted)]"> · {stateLabel(detail.status)}</span>
      </p>
      <h1 className="mt-2 font-[family-name:var(--font-newsreader)] text-4xl leading-tight font-medium">
        {detail.title}
      </h1>

      <section className="mt-8">
        <h2 className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">Evidence</h2>
        {detail.evidence ? (
          <figure className="mt-3 border-l-2 border-[var(--ink)] pl-4">
            {detail.evidence.source_label ? (
              <p className="text-sm font-medium">{detail.evidence.source_label}</p>
            ) : null}
            {detail.evidence.connection ? (
              <p className="mt-1 text-xs tracking-[0.14em] text-[var(--muted)] uppercase">{detail.evidence.connection}</p>
            ) : null}
            {detail.customer ? <p className="mt-3 text-sm">{detail.customer.name}</p> : null}
            <figcaption className="mt-3 text-xs tracking-[0.14em] text-[var(--muted)] uppercase">Customer message</figcaption>
            <blockquote className="mt-2 text-base leading-7 break-words">&ldquo;{detail.evidence.content}&rdquo;</blockquote>
            <p className="mt-3 text-sm text-[var(--muted)]">
              Received {formatDate(detail.evidence.occurred_at, detail.timezone)}
            </p>
          </figure>
        ) : (
          <p className="mt-3 text-sm text-[var(--muted)]">The original message is not attached to this item.</p>
        )}
        <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2">
          {detail.event ? (
            <div>
              <dt className="text-[var(--muted)]">Detected as</dt>
              <dd className="mt-1 font-medium">{detectedAs(detail.event.event_type)}</dd>
            </div>
          ) : null}
          {amount ? (
            <div>
              <dt className="text-[var(--muted)]">Amount</dt>
              <dd className="mt-1 font-medium tabular-nums">{amount}</dd>
            </div>
          ) : null}
          {due ? (
            <div>
              <dt className="text-[var(--muted)]">Due</dt>
              <dd className="mt-1 font-medium">{due}</dd>
            </div>
          ) : null}
          {detail.commitment ? (
            <div>
              <dt className="text-[var(--muted)]">Commitment</dt>
              <dd className="mt-1 font-medium">{stateLabel(detail.commitment.status)}</dd>
            </div>
          ) : null}
        </dl>
      </section>

      <section className="mt-8">
        <h2 className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">Why this matters</h2>
        <p className="mt-3 max-w-xl text-base leading-7 break-words">{whyItMatters(detail)}</p>
        {detail.financial_impact_amount && detail.currency ? (
          <p className="mt-3 text-sm">
            Revenue at risk{" "}
            <span className="font-semibold tabular-nums">
              {formatMoney(detail.financial_impact_amount, detail.currency)}
            </span>
          </p>
        ) : null}
      </section>

      <section className="mt-8" aria-labelledby="how-vigie-reached-this">
        <h2 id="how-vigie-reached-this" className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">
          How VIGIE reached this
        </h2>
        <ol className="mt-3 max-w-xl list-decimal space-y-2 pl-5 text-sm leading-6">
          {reachedSteps(detail.signal_type).map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </section>

      {detail.action ? (
        <section className="mt-8 border-t border-[var(--line)] pt-5">
          <h2 className="text-[11px] tracking-[0.14em] text-[var(--muted)] uppercase">Recommended action</h2>
          <p className="mt-2 text-base font-medium break-words">{detail.action.title ?? "Review the recommendation"}</p>
          <p className="mt-1 text-xs font-semibold tracking-[0.12em] uppercase">{stateLabel(detail.action.status)}</p>
          <Link
            href={actionHref(detail.action.id, detail.business_id)}
            className="mt-3 inline-block border border-[var(--ink)] px-3 py-1.5 text-sm font-medium"
          >
            Review recommendation
          </Link>
        </section>
      ) : null}

      {detail.customer ? (
        <section className="mt-8 border-t border-[var(--line)] pt-5">
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
