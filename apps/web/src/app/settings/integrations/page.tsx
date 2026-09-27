import type { Metadata } from "next";

import { IntegrationsLoader } from "@/components/integrations-loader";

export const metadata: Metadata = {
  title: "Integrations",
};

export default function IntegrationsPage() {
  return <IntegrationsLoader />;
}
