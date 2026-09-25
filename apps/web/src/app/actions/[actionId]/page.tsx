import { Suspense } from "react";

import { ActionReviewLoader } from "@/components/action-review-loader";
import { AppShell } from "@/components/app-shell";
import { DetailSkeleton } from "@/components/states";

export default function ActionPage() {
  return (
    <Suspense
      fallback={
        <AppShell>
          <DetailSkeleton />
        </AppShell>
      }
    >
      <ActionReviewLoader />
    </Suspense>
  );
}
