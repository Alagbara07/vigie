import type { ReactNode } from "react";

import { DemoControlsLoader } from "@/components/demo-controls";
import { BrandLink, PrimaryNav } from "@/components/primary-nav";
import { ProviderStatusLoader } from "@/components/provider-status";
import { SessionGate, SessionProvider } from "@/components/session-provider";
import { ThemeToggle } from "@/components/theme-toggle";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <div className="min-h-dvh bg-[var(--paper)] text-[var(--ink)]">
        <div className="mx-auto grid min-h-dvh w-full max-w-[1180px] md:grid-cols-[220px_minmax(0,1fr)]">
          <header className="min-w-0 border-b border-[var(--line)] px-5 py-4 md:border-b-0 md:border-r md:px-6 md:py-8">
            <div className="flex items-center justify-between gap-3">
              <BrandLink />
              <ThemeToggle />
            </div>
            <PrimaryNav />
            <ProviderStatusLoader />
            <DemoControlsLoader />
          </header>
          <div className="min-w-0 px-5 py-6 md:px-10 md:py-8">
            <SessionGate>{children}</SessionGate>
          </div>
        </div>
      </div>
    </SessionProvider>
  );
}
