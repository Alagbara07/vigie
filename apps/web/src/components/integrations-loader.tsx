"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { IntegrationsPanel, readDemoConnection } from "@/components/integrations-panel";
import { ErrorNotice } from "@/components/states";
import { loadSession } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { canManageIntegrations } from "@/lib/access";
import {
  connectWhatsapp,
  disconnectChannel,
  enableGmailListening,
  loadChannels,
  loadDemoMessages,
  oauthConnectPath,
  sendDemoMessage,
  syncGmail,
  syncMicrosoft,
  type ChannelStatus,
  type DemoConversation,
} from "@/lib/api/integrations";
import { loadDemoMode } from "@/lib/api/system";
import { connectionFailureDetail, type IntegrationIssue } from "@/lib/ux";

function oauthIssue(result: string | null, provider: string | null): IntegrationIssue | null {
  if (result !== "error") {
    return null;
  }
  return {
    provider: provider ?? "",
    detail: connectionFailureDetail(provider ?? ""),
    connection: true,
  };
}

export function IntegrationsLoader() {
  const searchParams = useSearchParams();
  const connectionResult = searchParams.get("connection");
  const connectionProvider = searchParams.get("provider");
  const [phase, setPhase] = useState<"loading" | "error" | "ready">("loading");
  const [demoEnabled, setDemoEnabled] = useState(false);
  const [businessId, setBusinessId] = useState<string | null>(null);
  const [canManage, setCanManage] = useState(false);
  const [recent, setRecent] = useState<DemoConversation[]>([]);
  const [channels, setChannels] = useState<ChannelStatus[]>([]);
  const [connected, setConnected] = useState(false);

  const load = useCallback(async () => {
    setPhase("loading");
    try {
      const [mode, session] = await Promise.all([loadDemoMode(), loadSession()]);
      const business = session.current_business;
      if (!business) {
        setPhase("error");
        return;
      }
      const active = mode.enabled && readDemoConnection();
      const [channelRows, recentRows] = await Promise.all([
        loadChannels(business.id),
        active ? loadDemoMessages(business.id) : Promise.resolve([]),
      ]);
      setDemoEnabled(mode.enabled);
      setBusinessId(business.id);
      setCanManage(canManageIntegrations(business.role));
      setConnected(active);
      setChannels(channelRows);
      setRecent(recentRows);
      setPhase("ready");
    } catch (error) {
      if (error instanceof ApiError || error instanceof Error) {
        setPhase("error");
      }
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    const refreshIfRestored = (event: PageTransitionEvent) => {
      if (event.persisted) {
        void load();
      }
    };
    window.addEventListener("pageshow", refreshIfRestored);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("pageshow", refreshIfRestored);
    };
  }, [load, connectionResult, connectionProvider]);

  return (
    <AppShell>
      {phase === "loading" ? <p className="sr-only">Loading your channels</p> : null}
      {phase === "error" ? (
        <ErrorNotice onRetry={() => void load()} title="VIGIE couldn't load your channels." detail="Try again." />
      ) : null}
      {phase === "ready" && businessId ? (
        <IntegrationsPanel
          demoEnabled={demoEnabled}
          initiallyConnected={connected}
          recent={recent}
          channels={channels}
          canManage={canManage}
          onRefresh={() => loadDemoMessages(businessId)}
          onConnectWhatsapp={async (phoneNumberId) => {
            await connectWhatsapp(businessId, phoneNumberId);
            setChannels(await loadChannels(businessId));
          }}
          onDisconnect={async (provider) => {
            await disconnectChannel(businessId, provider);
            setChannels(await loadChannels(businessId));
          }}
          onStartOauth={(provider) => {
            window.location.assign(oauthConnectPath(provider, businessId));
          }}
          onSync={async (provider) => {
            try {
              if (provider === "gmail") {
                await syncGmail(businessId);
              }
              if (provider === "microsoft365") {
                await syncMicrosoft(businessId);
              }
            } finally {
              try {
                setChannels(await loadChannels(businessId));
              } catch {
                // The sync error is the one the panel should show.
              }
            }
          }}
          onEnableListening={async (provider) => {
            if (provider === "gmail") {
              await enableGmailListening(businessId);
              setChannels(await loadChannels(businessId));
            }
          }}
          connectionIssue={oauthIssue(connectionResult, connectionProvider)}
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
