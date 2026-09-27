import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Sign up" };

export default function SignupPage() {
  return (
    <AppShell>
      <AuthForm mode="signup" />
    </AppShell>
  );
}
