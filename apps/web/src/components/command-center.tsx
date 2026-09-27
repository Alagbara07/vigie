"use client";

import Link from "next/link";
import { useState } from "react";

import { actionHref } from "@/lib/api/actions";
import type { DashboardSummary } from "@/lib/api/dashboard";
import {
  signalHref,
  type SignalKindFilter,
  type SignalRecord,
  type SignalStatusFilter,
} from "@/lib/api/signals";
import {
  conversationWhen,
  formatMoney,
  givenName,
  greetingFor,
  relativeTime,
  severityLabel,
} from "@/lib/format";
import { attentionHeadline, countOpen, PRODUCT_LINE, stateLabel, whatHappened, whyItMatters } from "@/lib/product";
import { EmptyAttention } from "@/components/states";

const KINDS: { id: SignalKindFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "risk", label: "Risks" },
  { id: "opportunity", label: "Opportunities" },
  { id: "operations", label: "Operations" },
];

const STATUSES: { id: SignalStatusFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "open", label: "Open" },
  { id: "resolved", label: "Resolved" },
];

type CommandCenterProps = {
  summary: DashboardSummary;
  signals: SignalRecord[];
  now?: Date;
};

export function CommandCenter({ summary, signals, now = new Date() }: CommandCenterProps) {
  const [kind, setKind] = useState<SignalKindFilter>("all");
  const [status, setStatus] = useState<SignalStatusFilter>("open");
  const visible = signals
    .filter((signal) => kind === "all" || signal.attention_group === kind)
    .filter((signal) => matchesStatus(signal.status, status))
    .sort(byImportance);
  const caughtUp = summary.open_signals === 0 && (status === "open" || status === "all") && kind === "all";
  const overduePayments = countOpen(signals, "OVERDUE_PAYMENT");
  const waitingRequests = countOpen(signals, "UNANSWERED_REQUEST");

  return (
    <div>
      <header>
        <p className="text-xs font-semibold tracking-[0.22em]">VIGIE</p>
        <p className="mt-2 text-sm text-[var(--muted)]">L&apos;intelligence qui veille sur votre entreprise.</p>
        <h1 className="mt-8 font-[family-name:var(--font-newsreader)] text-4xl leading-tight font-medium tracking-tight">
          {greetingFor(now, summary.timezone)}, {givenName(summary.business_name)}.
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-[var(--ink)]">{PRODUCT_LINE}</p>
      </header>

      <section aria-labelledby="attention-summary" className="mt-8">
        <h2 id="attention-summary" className="font-[family-name:var(--font-newsreader)] text-3xl leading-tight font-medium">
          {summary.open_signals === 0 ? "You're all caught up." : attentionHeadline(summary.open_signals)}
        </h2>
        <dl className="mt-5 grid grid-cols-1 gap-px border border-[var(--line)] bg-[var(--line)] sm:grid-cols-3">
          <Stat value={formatMoney(summary.revenue_at_risk, summary.currency)} label="Revenue at risk" />
          <Stat
            value={String(overduePayments)}
            label={overduePayments === 1 ? "Overdue payment" : "Overdue payments"}
          />
          <Stat
            value={String(waitingRequests)}
            label={waitingRequests === 1 ? "Customer request waiting" : "Customer requests waiting"}
          />
        </dl>
      </section>

      <div className="mt-10 grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_280px]">
        <section aria-labelledby="signal-feed">
          <h2 id="signal-feed" className="text-lg font-semibold">
            What needs attention
          </h2>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <FilterGroup label="Signal kind" value={kind} options={KINDS} onChange={setKind} />
            <FilterGroup label="Signal status" value={status} options={STATUSES} onChange={setStatus} />
          </div>
          <div className="mt-4">
            {visible.length === 0 && caughtUp ? <EmptyAttention /> : null}
            {visible.length === 0 && !caughtUp ? (
              <p className="border border-[var(--line)] bg-[var(--panel)] px-5 py-6 text-sm text-[var(--muted)]">
                Nothing in this view. Try another filter.
              </p>
            ) : null}
            {visible.length > 0 ? (
              <ol className="border-t border-[var(--line)]">
                {visible.map((signal) => (
                  <SignalRow key={signal.id} signal={signal} businessId={summary.business_id} now={now} />
                ))}
              </ol>
            ) : null}
          </div>
        </section>
        <RecentConversations summary={summary} now={now} />
      </div>
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="bg-[var(--panel)] px-4 py-4">
      <dd className="text-2xl font-semibold tabular-nums">{value}</dd>
      <dt className="mt-1 text-sm text-[var(--muted)]">{label}</dt>
    </div>
  );
}

function FilterGroup<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { id: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1">
      {options.map((option) => {
        const selected = option.id === value;
        return (
          <button
            key={option.id}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(option.id)}
            className={`px-2.5 py-1 text-sm ${
              selected ? "bg-[var(--ink)] text-[var(--paper)]" : "text-[var(--muted)]"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function SignalRow({
  signal,
  businessId,
  now,
}: {
  signal: SignalRecord;
  businessId: string;
  now: Date;
}) {
  const tone = severityLabel(signal.severity);
  const href = signalHref(signal.id, businessId);
  return (
    <li className={`border-b border-[var(--line)] border-l-2 py-5 pl-4 ${toneClass(tone.tone)}`}>
      <p className={`text-[11px] font-semibold tracking-[0.14em] uppercase ${toneText(tone.tone)}`}>
        {tone.label}
        <span className="text-[var(--muted)]"> · {stateLabel(signal.status)}</span>
      </p>
      <h3 className="mt-1 text-lg font-semibold">{signal.title}</h3>
      <dl className="mt-4 max-w-xl space-y-3 text-sm leading-6">
        <div>
          <dt className="text-[11px] tracking-[0.14em] text-[var(--muted)] uppercase">What happened</dt>
          <dd className="mt-1 break-words">{whatHappened(signal)}</dd>
        </div>
        <div>
          <dt className="text-[11px] tracking-[0.14em] text-[var(--muted)] uppercase">Customer</dt>
          <dd className="mt-1">{signal.customer_name ?? "Customer"}</dd>
        </div>
        <div>
          <dt className="text-[11px] tracking-[0.14em] text-[var(--muted)] uppercase">Why this matters</dt>
          <dd className="mt-1 break-words text-[var(--muted)]">{whyItMatters(signal)}</dd>
        </div>
      </dl>
      <p className="mt-3 text-xs text-[var(--muted)]">{relativeTime(signal.created_at, now)}</p>
      <Link href={href} className="mt-3 inline-block text-sm font-medium underline-offset-4 hover:underline">
        View evidence
      </Link>
      {signal.action ? (
        <div className="mt-4 border-t border-[var(--line)] pt-3">
          <p className="text-[11px] tracking-[0.14em] text-[var(--muted)] uppercase">Recommended</p>
          <p className="mt-1 text-sm break-words">{signal.action.title ?? "Review the recommendation"}</p>
          <p className="mt-1 text-xs font-semibold tracking-[0.12em] uppercase">{stateLabel(signal.action.status)}</p>
          <Link
            href={actionHref(signal.action.id, businessId)}
            className="mt-2 inline-block border border-[var(--ink)] px-3 py-1.5 text-sm font-medium"
          >
            Review recommendation
          </Link>
        </div>
      ) : null}
    </li>
  );
}

function RecentConversations({ summary, now }: { summary: DashboardSummary; now: Date }) {
  return (
    <aside aria-labelledby="recent-conversations">
      <h2 id="recent-conversations" className="text-sm font-semibold">
        Recent conversations
      </h2>
      <p className="mt-1 text-sm text-[var(--muted)]">Not every conversation needs attention.</p>
      {summary.recent_conversations.length === 0 ? (
        <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
          No conversations yet. Connect a channel to start bringing conversations into VIGIE.
        </p>
      ) : (
        <ol className="mt-3 divide-y divide-[var(--line)] border-y border-[var(--line)]">
          {summary.recent_conversations.map((conversation) => (
            <li key={conversation.conversation_id} className="py-3">
              <p className="text-sm font-medium">{conversation.customer_name}</p>
              <p className="mt-1 line-clamp-2 text-sm text-[var(--muted)]">&ldquo;{conversation.last_message}&rdquo;</p>
              <p className="mt-1 text-xs text-[var(--muted)]">
                {conversationWhen(conversation.last_message_at, summary.timezone, now)}
              </p>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}

function matchesStatus(status: string, filter: SignalStatusFilter): boolean {
  if (filter === "all") {
    return true;
  }
  if (filter === "open") {
    return status === "OPEN";
  }
  return status === "RESOLVED";
}

function byImportance(left: SignalRecord, right: SignalRecord): number {
  return severityRank(left.severity) - severityRank(right.severity);
}

function severityRank(severity: string): number {
  if (severity === "CRITICAL") {
    return 0;
  }
  if (severity === "HIGH") {
    return 1;
  }
  if (severity === "MEDIUM") {
    return 2;
  }
  return 3;
}

function toneClass(tone: "high" | "medium" | "low"): string {
  if (tone === "high") {
    return "border-l-[var(--high)] bg-[var(--high-soft)]";
  }
  if (tone === "medium") {
    return "border-l-[var(--medium)] bg-[var(--medium-soft)]";
  }
  return "border-l-[var(--line)] bg-[var(--panel)]";
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
