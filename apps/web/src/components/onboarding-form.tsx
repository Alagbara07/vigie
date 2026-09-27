"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { AuthError, createBusiness } from "@/lib/api/auth";

export function OnboardingForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await createBusiness(name);
      router.push("/");
    } catch (caught) {
      setError(caught instanceof AuthError ? caught.message : "VIGIE couldn't create the business.");
      setPending(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="max-w-md border border-[var(--line)] bg-[var(--panel)] px-5 py-6">
      <p className="text-xs font-semibold tracking-[0.22em]">VIGIE</p>
      <h1 className="mt-4 font-[family-name:var(--font-newsreader)] text-4xl leading-tight font-medium">
        Create your business
      </h1>
      <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
        You become the owner. You can add another business later.
      </p>
      <label className="mt-6 block text-sm" htmlFor="business-name">
        Business name
        <input
          id="business-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="mt-2 w-full border border-[var(--line)] bg-[var(--paper)] px-3 py-2 text-sm text-[var(--ink)]"
        />
      </label>
      <button
        type="submit"
        disabled={pending || name.trim().length === 0}
        className="mt-6 border border-[var(--ink)] bg-[var(--ink)] px-4 py-2 text-sm font-medium text-[var(--paper)] disabled:opacity-60"
      >
        {pending ? "Creating your business..." : "Create business"}
      </button>
      {error ? (
        <p className="mt-4 text-sm text-[var(--high)]" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
