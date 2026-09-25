import { Suspense } from "react";

import { AppShell } from "@/components/app-shell";
import { SignalDetailLoader } from "@/components/signal-detail-loader";
import { DetailSkeleton } from "@/components/states";

export default function SignalPage() {
  return (
    <Suspense
      fallback={
        <AppShell>
          <DetailSkeleton />
        </AppShell>
      }
    >
      <SignalDetailLoader />
    </Suspense>
  );
}
