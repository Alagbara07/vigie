import Link from "next/link";
import type { ReactNode } from "react";

import { DemoControlsLoader } from "@/components/demo-controls";
import { ProviderStatusLoader } from "@/components/provider-status";

const NAV = [
  { label: "Command Center", href: "/", ready: true },
  { label: "Conversations", ready: false },
  { label: "Customers", ready: false },
  { label: "Signals", ready: false },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-[var(--paper)] text-[var(--ink)]">
      <div className="mx-auto grid min-h-dvh w-full max-w-[1180px] md:grid-cols-[220px_minmax(0,1fr)]">
        <header className="min-w-0 border-b border-[var(--line)] px-5 py-4 md:border-b-0 md:border-r md:px-6 md:py-8">
          <Link href="/" className="text-sm font-semibold tracking-[0.22em]">
            VIGIE
          </Link>
          <nav aria-label="Primary" className="mt-4 flex flex-wrap gap-x-4 gap-y-1 md:mt-8 md:flex-col md:gap-1">
            {NAV.map((item) =>
              item.ready ? (
                <Link
                  key={item.label}
                  href={item.href}
                  aria-current="page"
                  className="shrink-0 py-1 text-sm font-medium"
                >
                  {item.label}
                </Link>
              ) : (
                <span
                  key={item.label}
                  className="flex shrink-0 items-center gap-2 py-1 text-sm text-[var(--muted)]"
                >
                  {item.label}
                  <span className="text-[10px] tracking-[0.14em] uppercase">Later</span>
                </span>
              ),
            )}
          </nav>
          <ProviderStatusLoader />
          <DemoControlsLoader />
        </header>
        <div className="min-w-0 px-5 py-6 md:px-10 md:py-8">{children}</div>
      </div>
    </div>
  );
}
