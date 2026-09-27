"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { logout } from "@/lib/api/auth";
import { useSession } from "@/components/session-provider";

const NAV = [
  { href: "/", label: "Command Center" },
  { href: "/demo", label: "Demo" },
  { href: "/about", label: "About" },
  { href: "/settings/integrations", label: "Integrations" },
] as const;

export function PrimaryNav() {
  const pathname = usePathname();
  const { session } = useSession();
  const signedIn = session != null;

  async function signOut() {
    await logout();
    // A full load drops the in-memory session after the cookie is revoked.
    // Client-side push keeps the previous session and can be cancelled by that re-render.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  }

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
      {signedIn ? (
        <button type="button" onClick={() => void signOut()} className="py-1 text-left text-sm text-[var(--muted)]">
          Log out
        </button>
      ) : (
        <Link href="/login" className="py-1 text-sm text-[var(--muted)]">
          Sign in
        </Link>
      )}
    </nav>
  );
}
