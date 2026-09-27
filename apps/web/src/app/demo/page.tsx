import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { DemoEntry } from "@/components/demo-entry";

export const metadata: Metadata = {
  title: "Demo",
};

const STEPS = [
  "Customer conversation",
  "VIGIE understanding",
  "Commitment",
  "Missed deadline",
  "Signal",
  "Recommendation",
  "Human approval",
];

export default function DemoPage() {
  return (
    <AppShell>
      <article className="max-w-2xl">
        <p className="text-xs font-semibold tracking-[0.22em]">VIGIE</p>
        <h1 className="mt-4 font-[family-name:var(--font-newsreader)] text-4xl leading-tight font-medium">
          From a conversation to a decision.
        </h1>
        <p className="mt-6 text-base leading-7">
          VIGIE does not answer a question and forget it. A conversation becomes a commitment. Time passes. The
          condition changes. Then you see a signal and a recommendation, and you decide.
        </p>
        <ol className="mt-8 space-y-2">
          {STEPS.map((step, index) => (
            <li key={step} className="text-base">
              <span className="mr-3 text-sm text-[var(--muted)] tabular-nums">{index + 1}</span>
              {step}
            </li>
          ))}
        </ol>
        <section className="mt-10 border-t border-[var(--line)] pt-6">
          <h2 className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">What does not become an alert</h2>
          <p className="mt-3 text-sm leading-6">
            &ldquo;I sent the ₦150,000 balance yesterday.&rdquo; is a payment claim. It is not a verified payment.
          </p>
          <p className="mt-3 text-sm leading-6">&ldquo;Good morning.&rdquo; does not create a signal.</p>
        </section>
        <DemoEntry />
        <p className="mt-4 text-sm text-[var(--muted)]">Try Demo opens the seeded Adaeze Wears story. Sign In is for your own business.</p>
      </article>
    </AppShell>
  );
}
