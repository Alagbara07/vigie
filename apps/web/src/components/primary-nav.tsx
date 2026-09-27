"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Command Center" },
  { href: "/demo", label: "Demo" },
  { href: "/about", label: "About" },
  { href: "/settings/integrations", label: "Integrations" },
] as const;

export function PrimaryNav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary" className="mt-4 flex flex-wrap gap-x-4 gap-y-1 md:mt-8 md:flex-col md:gap-1">
      {NAV.map((item) => {
        const current = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={current ? "page" : undefined}
            className={`shrink-0 py-1 text-sm hover:text-[var(--ink)] ${current ? "font-medium" : "text-[var(--muted)]"}`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
