import { Suspense } from "react";
import type { Metadata } from "next";

import { IntegrationsLoader } from "@/components/integrations-loader";

export const metadata: Metadata = {
  title: "Integrations",
};

export default function IntegrationsPage() {
  return (
    <Suspense fallback={<p className="sr-only">Loading your channels</p>}>
      <IntegrationsLoader />
    </Suspense>
  );
}
