"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { AuthError, login, signup, type SessionState } from "@/lib/api/auth";

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const signingUp = mode === "signup";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const session = signingUp ? await signup({ name, email, password }) : await login({ email, password });
      router.push(destination(session));
    } catch (caught) {
      setError(caught instanceof AuthError ? caught.message : "VIGIE couldn't complete that request.");
      setPending(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="max-w-md border border-[var(--line)] bg-[var(--panel)] px-5 py-6">
      <p className="text-xs font-semibold tracking-[0.22em]">VIGIE</p>
      <h1 className="mt-4 font-[family-name:var(--font-newsreader)] text-4xl leading-tight font-medium">
        {signingUp ? "Create your account" : "Sign in"}
      </h1>
      <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
        {signingUp
          ? "This account is separate from the demo. You will create a business next."
          : "Use your VIGIE account. The demo story stays on its own entry."}
      </p>
      {signingUp ? (
        <label className="mt-6 block text-sm" htmlFor="auth-name">
          Name
          <input
            id="auth-name"
            value={name}
            autoComplete="name"
            onChange={(event) => setName(event.target.value)}
            className="mt-2 w-full border border-[var(--line)] bg-[var(--paper)] px-3 py-2 text-sm text-[var(--ink)]"
          />
        </label>
      ) : null}
      <label className="mt-4 block text-sm" htmlFor="auth-email">
        Email
        <input
          id="auth-email"
          type="email"
          value={email}
          autoComplete="email"
          onChange={(event) => setEmail(event.target.value)}
          className="mt-2 w-full border border-[var(--line)] bg-[var(--paper)] px-3 py-2 text-sm text-[var(--ink)]"
        />
      </label>
      <label className="mt-4 block text-sm" htmlFor="auth-password">
        Password
        <input
          id="auth-password"
          type="password"
          value={password}
          autoComplete={signingUp ? "new-password" : "current-password"}
          onChange={(event) => setPassword(event.target.value)}
          className="mt-2 w-full border border-[var(--line)] bg-[var(--paper)] px-3 py-2 text-sm text-[var(--ink)]"
        />
      </label>
      <button
        type="submit"
        disabled={pending}
        className="mt-6 border border-[var(--ink)] bg-[var(--ink)] px-4 py-2 text-sm font-medium text-[var(--paper)] disabled:opacity-60"
      >
        {pending ? "Please wait" : signingUp ? "Create account" : "Sign in"}
      </button>
      {error ? (
        <p className="mt-4 text-sm text-[var(--high)]" role="alert">
          {error}
        </p>
      ) : null}
      <p className="mt-6 text-sm">
        {signingUp ? (
          <Link href="/login" className="underline-offset-4 hover:underline">
            Sign in
          </Link>
        ) : (
          <Link href="/signup" className="underline-offset-4 hover:underline">
            Create an account
          </Link>
        )}
      </p>
      <p className="mt-3 text-sm">
        <Link href="/demo" className="text-[var(--muted)] underline-offset-4 hover:underline">
          Try Demo
        </Link>
      </p>
    </form>
  );
}

function destination(session: SessionState): string {
  return session.current_business ? "/" : "/onboarding";
}
