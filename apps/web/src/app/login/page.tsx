import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <AppShell>
      <AuthForm mode="login" />
    </AppShell>
  );
}
