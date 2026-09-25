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

  return (
    <div>
      <header>
        <p className="text-xs font-semibold tracking-[0.22em]">VIGIE</p>
        <p className="mt-2 text-sm text-[var(--muted)]">L&apos;intelligence qui veille sur votre entreprise.</p>
        <h1 className="mt-8 font-[family-name:var(--font-newsreader)] text-4xl leading-tight font-medium tracking-tight">
          {greetingFor(now, summary.timezone)}, {givenName(summary.business_name)}.
        </h1>
        <p className="mt-2 text-lg text-[var(--muted)]">Here&apos;s what needs your attention.</p>
      </header>

      <section aria-labelledby="attention-summary" className="mt-8">
        <h2 id="attention-summary" className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">
          Attention required
        </h2>
        <dl className="mt-3 grid grid-cols-2 gap-px border border-[var(--line)] bg-[var(--line)] lg:grid-cols-4">
          <Stat value={String(summary.open_signals)} label="Open signals" />
          <Stat value={String(summary.high_priority_signals)} label="High priority" />
          <Stat value={formatMoney(summary.revenue_at_risk, summary.currency)} label="Revenue at risk" />
          <Stat value={String(summary.missed_commitments)} label="Missed commitments" />
        </dl>
      </section>

      <div className="mt-10 grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_280px]">
        <section aria-labelledby="signal-feed">
          <h2 id="signal-feed" className="text-lg font-semibold">
            Needs your attention
          </h2>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <FilterGroup label="Signal kind" value={kind} options={KINDS} onChange={setKind} />
            <FilterGroup label="Signal status" value={status} options={STATUSES} onChange={setStatus} />
          </div>
          <div className="mt-4">
            {visible.length === 0 && caughtUp ? <EmptyAttention /> : null}
            {visible.length === 0 && !caughtUp ? (
              <p className="border border-[var(--line)] bg-[var(--panel)] px-5 py-6 text-sm text-[var(--muted)]">
                Nothing matches this view.
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
      <p className={`text-[11px] font-semibold tracking-[0.14em] uppercase ${toneText(tone.tone)}`}>{tone.label}</p>
      <h3 className="mt-1 text-lg font-semibold">{signal.title}</h3>
      <p className="mt-2 max-w-xl text-sm leading-6 text-[var(--muted)]">{signal.description}</p>
      {signal.financial_impact_amount && signal.currency ? (
        <p className="mt-3 text-sm">
          <span className="text-[var(--muted)]">Revenue at risk </span>
          <span className="font-semibold tabular-nums">
            {formatMoney(signal.financial_impact_amount, signal.currency)}
          </span>
        </p>
      ) : null}
      <p className="mt-3 text-xs text-[var(--muted)]">
        {signal.customer_name ?? "Customer"}
        <span aria-hidden="true"> · </span>
        {relativeTime(signal.created_at, now)}
      </p>
      <Link href={href} className="mt-3 inline-block text-sm font-medium underline-offset-4 hover:underline">
        View details
      </Link>
      {signal.action ? (
        <div className="mt-4 border-t border-[var(--line)] pt-3">
          <p className="text-[11px] tracking-[0.14em] text-[var(--muted)] uppercase">Recommended action</p>
          <p className="mt-1 text-sm">{signal.action.title ?? "Review the recommendation"}</p>
          <Link
            href={actionHref(signal.action.id, businessId)}
            className="mt-2 inline-block text-sm font-medium underline-offset-4 hover:underline"
          >
            Review action
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
      {summary.recent_conversations.length === 0 ? (
        <p className="mt-3 text-sm text-[var(--muted)]">No conversations yet.</p>
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
