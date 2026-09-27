"use client";

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

export function IntegrationsLoader() {
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
            if (provider === "gmail") {
              await syncGmail(businessId);
              setChannels(await loadChannels(businessId));
            }
            if (provider === "microsoft365") {
              await syncMicrosoft(businessId);
              setChannels(await loadChannels(businessId));
            }
          }}
          onEnableListening={async (provider) => {
            if (provider === "gmail") {
              await enableGmailListening(businessId);
              setChannels(await loadChannels(businessId));
            }
          }}
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
