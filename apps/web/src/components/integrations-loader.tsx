"use client";

import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { IntegrationsPanel, readDemoConnection } from "@/components/integrations-panel";
import { ErrorNotice } from "@/components/states";
import { loadDemoBusiness } from "@/lib/api/businesses";
import { ApiError, MissingBusinessError } from "@/lib/api/client";
import { loadDemoMessages, sendDemoMessage, type DemoConversation } from "@/lib/api/integrations";
import { loadDemoMode } from "@/lib/api/system";

export function IntegrationsLoader() {
  const [phase, setPhase] = useState<"loading" | "error" | "ready">("loading");
  const [demoEnabled, setDemoEnabled] = useState(false);
  const [businessId, setBusinessId] = useState<string | null>(null);
  const [recent, setRecent] = useState<DemoConversation[]>([]);
  const [connected, setConnected] = useState(false);

  const load = useCallback(async () => {
    setPhase("loading");
    try {
      const [mode, business] = await Promise.all([loadDemoMode(), loadDemoBusiness()]);
      const active = mode.enabled && readDemoConnection();
      setDemoEnabled(mode.enabled);
      setBusinessId(business.id);
      setConnected(active);
      setRecent(active ? await loadDemoMessages(business.id) : []);
      setPhase("ready");
    } catch (error) {
      if (error instanceof MissingBusinessError || error instanceof ApiError || error instanceof Error) {
        setPhase("error");
      }
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <AppShell>
      {phase === "loading" ? <p className="sr-only">Opening channels</p> : null}
      {phase === "error" ? <ErrorNotice onRetry={() => void load()} title="VIGIE couldn't load your channels." /> : null}
      {phase === "ready" && businessId ? (
        <IntegrationsPanel
          demoEnabled={demoEnabled}
          initiallyConnected={connected}
          recent={recent}
          onRefresh={() => loadDemoMessages(businessId)}
          onSend={async ({ customerName, text }) => {
            const slug = customerName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "customer";
            return sendDemoMessage({
              businessId,
              customerName,
              text,
              conversationId: `demo-${slug}`,
              externalMessageId: `demo-${crypto.randomUUID()}`,
            });
          }}
        />
      ) : null}
    </AppShell>
  );
}
