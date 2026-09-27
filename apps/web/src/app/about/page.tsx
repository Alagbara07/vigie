import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";

export const metadata: Metadata = {
  title: "About",
};

export default function AboutPage() {
  return (
    <AppShell>
      <article className="max-w-2xl">
        <p className="text-xs font-semibold tracking-[0.22em]">VIGIE</p>
        <h1 className="mt-4 font-[family-name:var(--font-newsreader)] text-4xl leading-tight font-medium">
          Business intelligence that watches what matters.
        </h1>
        <p className="mt-6 text-base leading-7">
          Important commitments, customer requests and business risks often disappear inside everyday conversations.
          VIGIE turns those conversations into business memory, watches what changes over time, and tells you what
          needs attention.
        </p>
        <ol className="mt-10 divide-y divide-[var(--line)] border-y border-[var(--line)]">
          <li className="py-5">
            <h2 className="text-xs font-semibold tracking-[0.16em]">Remember</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
              Turn conversations into commitments and requests that stay on record.
            </p>
          </li>
          <li className="py-5">
            <h2 className="text-xs font-semibold tracking-[0.16em]">Detect</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
              Find the commitments and requests that need attention as time passes.
            </p>
          </li>
          <li className="py-5">
            <h2 className="text-xs font-semibold tracking-[0.16em]">Recommend</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
              Suggest the next action. You decide. Nothing is sent on its own.
            </p>
          </li>
        </ol>
      </article>
    </AppShell>
  );
}
