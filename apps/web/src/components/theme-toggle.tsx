"use client";

import { useEffect, useRef } from "react";

import { applyTheme, readTheme, type ThemeChoice } from "@/lib/theme";

function labelFor(theme: ThemeChoice): string {
  return theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
}

export function ThemeToggle() {
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    buttonRef.current?.setAttribute("aria-label", labelFor(readTheme()));
  }, []);

  function toggle() {
    const next: ThemeChoice = readTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    buttonRef.current?.setAttribute("aria-label", labelFor(next));
  }

  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={toggle}
      aria-label="Switch to dark mode"
      className="inline-flex items-center gap-1.5 border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-xs font-medium text-[var(--ink)] hover:bg-[var(--paper)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ink)]"
    >
      <span className="theme-offer-dark" aria-hidden="true">
        ☾ Dark
      </span>
      <span className="theme-offer-light" aria-hidden="true">
        ☀ Light
      </span>
    </button>
  );
}
