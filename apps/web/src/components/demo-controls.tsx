"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api/client";
import { loadDemoMode, resetDemo, runDemo } from "@/lib/api/system";

export function DemoControlsLoader() {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadDemoMode()
        .then((mode) => setEnabled(mode.enabled))
        .catch(() => setEnabled(false));
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  if (!enabled) {
    return null;
  }
  return <DemoControls />;
}

export function DemoControls({
  onRun = runDemo,
  onReset = resetDemo,
}: {
  onRun?: () => Promise<unknown>;
  onReset?: () => Promise<unknown>;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [pending, setPending] = useState<"run" | "reset" | null>(null);
  const [failed, setFailed] = useState(false);

  async function perform(kind: "run" | "reset", operation: () => Promise<unknown>) {
    setFailed(false);
    setPending(kind);
    try {
      await operation();
      if (pathname === "/") {
        window.location.reload();
        return;
      }
      router.push("/");
    } catch (error) {
      if (error instanceof ApiError || error instanceof Error) {
        setFailed(true);
        setPending(null);
      }
    }
  }

  return (
    <section className="mt-8 border-t border-[var(--line)] pt-4" aria-label="Demo">
      <p className="text-[10px] font-semibold tracking-[0.16em] text-[var(--muted)] uppercase">Demo mode</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={pending !== null}
          onClick={() => void perform("run", onRun)}
          className="border border-[var(--ink)] px-2 py-1 text-xs font-medium disabled:opacity-60"
        >
          {pending === "run" ? "Running" : "Run demo"}
        </button>
        <button
          type="button"
          disabled={pending !== null}
          onClick={() => void perform("reset", onReset)}
          className="border border-[var(--line)] px-2 py-1 text-xs text-[var(--muted)] disabled:opacity-60"
        >
          {pending === "reset" ? "Resetting" : "Reset demo"}
        </button>
      </div>
      {failed ? <p className="mt-2 text-xs text-[var(--muted)]">The demo could not be prepared.</p> : null}
    </section>
  );
}
