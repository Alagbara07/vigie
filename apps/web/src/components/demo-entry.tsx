"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthError, enterDemo } from "@/lib/api/auth";

export function DemoEntry() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function start() {
    setPending(true);
    setError(null);
    try {
      await enterDemo();
      router.push("/");
    } catch (caught) {
      setError(caught instanceof AuthError ? caught.message : "Demo mode is not available.");
      setPending(false);
    }
  }

  return (
    <div className="mt-8 flex flex-wrap items-center gap-4">
      <button
        type="button"
        disabled={pending}
        onClick={() => void start()}
        className="border border-[var(--ink)] bg-[var(--ink)] px-4 py-2 text-sm font-medium text-[var(--paper)] disabled:opacity-60"
      >
        {pending ? "Please wait" : "Try Demo"}
      </button>
      <Link href="/login" className="text-sm font-medium underline-offset-4 hover:underline">
        Sign In
      </Link>
      {error ? (
        <p className="w-full text-sm text-[var(--high)]" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
