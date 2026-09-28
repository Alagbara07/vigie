"use client";

import { useState, type FormEvent } from "react";

import { ApiError } from "@/lib/api/client";
import {
  understanding,
  type ChannelStatus,
  type DemoConversation,
  type DemoInboundResult,
} from "@/lib/api/integrations";
import {
  connectionFailureDetail,
  connectionFailureHeadline,
  integrationView,
  knownApiDetail,
  type IntegrationIssue,
  type IntegrationView,
} from "@/lib/ux";

const CONNECTION_KEY = "vigie-demo-whatsapp";

const DEFAULT_CHANNELS: ChannelStatus[] = [
  {
    provider: "whatsapp",
    label: "WhatsApp Business",
    description: "Monitor customer conversations and identify commitments, payment claims and requests.",
    availability: "not_configured",
    accountLabel: null,
    lastSyncAt: null,
    lastError: null,
    configured: false,
  },
  {
    provider: "gmail",
    label: "Google Workspace",
    description: "Analyze business email conversations.",
    availability: "not_configured",
    accountLabel: null,
    lastSyncAt: null,
    lastError: null,
    configured: false,
  },
  {
    provider: "microsoft365",
    label: "Microsoft 365",
    description: "Analyze Outlook business conversations.",
    availability: "not_configured",
    accountLabel: null,
    lastSyncAt: null,
    lastError: null,
    configured: false,
  },
];

type SendInput = {
  customerName: string;
  text: string;
};

export function IntegrationsPanel({
  demoEnabled,
  initiallyConnected = false,
  recent = [],
  channels = DEFAULT_CHANNELS,
  onSend,
  onRefresh,
  onConnectWhatsapp,
  onDisconnect,
  onStartOauth,
  onSync,
  onEnableListening,
  canManage = true,
  connectionIssue = null,
}: {
  demoEnabled: boolean;
  initiallyConnected?: boolean;
  recent?: DemoConversation[];
  channels?: ChannelStatus[];
  onSend: (input: SendInput) => Promise<DemoInboundResult>;
  onRefresh?: () => Promise<DemoConversation[]>;
  onConnectWhatsapp?: (phoneNumberId: string) => Promise<void>;
  onDisconnect?: (provider: string) => Promise<void>;
  onStartOauth?: (provider: string) => void;
  onSync?: (provider: string) => Promise<void>;
  onEnableListening?: (provider: string) => Promise<void>;
  canManage?: boolean;
  connectionIssue?: IntegrationIssue | null;
}) {
  const [connected, setConnected] = useState(initiallyConnected && demoEnabled);
  const [customerName, setCustomerName] = useState("Amaka Bello");
  const [text, setText] = useState("I'll pay the remaining ₦150,000 on Friday.");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [messages, setMessages] = useState(recent);
  const [phase, setPhase] = useState<"idle" | "pending" | "sent" | "error">("idle");
  const [notice, setNotice] = useState<string | null>(null);
  const [localIssue, setLocalIssue] = useState<IntegrationIssue | null>(null);
  const [busy, setBusy] = useState<{ provider: string; action: "connect" | "sync" | "disconnect" | "listen" } | null>(
    null,
  );

  async function connectDemo() {
    if (!demoEnabled) {
      return;
    }
    window.localStorage.setItem(CONNECTION_KEY, "active");
    setConnected(true);
    if (onRefresh) {
      setMessages(await onRefresh());
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!customerName.trim() || !text.trim()) {
      setNotice("Enter a customer and a message.");
      setPhase("error");
      return;
    }
    setPhase("pending");
    setNotice(null);
    try {
      const result = await onSend({ customerName: customerName.trim(), text: text.trim() });
      setPhase("sent");
      setNotice("Message received. Analyzing the conversation...");
      if (onRefresh) {
        setMessages(await onRefresh());
      } else {
        setMessages((current) => [
          {
            message_id: result.message_id,
            customer_name: result.customer_name,
            text: result.text,
            occurred_at: result.occurred_at,
            source_label: result.source_label,
            connection: result.connection,
            events: result.events,
          },
          ...current,
        ]);
      }
    } catch (error) {
      setPhase("error");
      setNotice(
        error instanceof ApiError && error.status === 404
          ? "The demo connector is not available."
          : "VIGIE couldn't receive that message. Try again.",
      );
    }
  }

  function reportIssue(provider: string, detail: string, connection: boolean) {
    setLocalIssue({ provider, detail, connection });
  }

  async function connectChannel(channel: ChannelStatus) {
    if (!channel.configured) {
      reportIssue(channel.provider, connectionFailureDetail(channel.provider), true);
      return;
    }
    if (channel.provider === "whatsapp") {
      if (!phoneNumberId.trim()) {
        reportIssue(channel.provider, "Enter the WhatsApp phone number ID.", false);
        return;
      }
      if (!onConnectWhatsapp) {
        reportIssue(channel.provider, connectionFailureDetail(channel.provider), true);
        return;
      }
      setBusy({ provider: channel.provider, action: "connect" });
      setLocalIssue(null);
      try {
        await onConnectWhatsapp(phoneNumberId.trim());
        setLocalIssue(null);
      } catch (error) {
        reportIssue(
          channel.provider,
          error instanceof ApiError && error.status === 409
            ? connectionFailureDetail(channel.provider)
            : connectionFailureDetail("whatsapp"),
          true,
        );
      } finally {
        setBusy(null);
      }
      return;
    }
    if (!onStartOauth) {
      reportIssue(channel.provider, connectionFailureDetail(channel.provider), true);
      return;
    }
    setBusy({ provider: channel.provider, action: "connect" });
    onStartOauth(channel.provider);
  }

  async function runChannelAction(
    provider: string,
    action: (() => Promise<void>) | undefined,
    failure: string,
    kind: "sync" | "listen",
    unconfigured?: string,
  ) {
    if (!action) {
      return;
    }
    setBusy({ provider, action: kind });
    setLocalIssue(null);
    try {
      await action();
    } catch (error) {
      const known = error instanceof ApiError ? knownApiDetail(error.detail) : null;
      reportIssue(
        provider,
        known ?? (error instanceof ApiError && error.status === 409 && unconfigured ? unconfigured : failure),
        false,
      );
    } finally {
      setBusy(null);
    }
  }

  async function disconnectChannel(channel: ChannelStatus) {
    if (!onDisconnect) {
      return;
    }
    setBusy({ provider: channel.provider, action: "disconnect" });
    setLocalIssue(null);
    try {
      await onDisconnect(channel.provider);
    } catch {
      reportIssue(channel.provider, "VIGIE couldn't disconnect that channel. Try again.", false);
    } finally {
      setBusy(null);
    }
  }

  function issueFor(provider: string): IntegrationIssue | null {
    if (localIssue?.provider === provider) {
      return localIssue;
    }
    if (connectionIssue?.provider === provider) {
      return connectionIssue;
    }
    return null;
  }

  const realChannels = channels.filter((channel) => channel.provider !== "demo");

  return (
    <article className="max-w-3xl">
      <p className="text-xs font-semibold tracking-[0.22em]">VIGIE</p>
      <h1 className="mt-4 font-[family-name:var(--font-newsreader)] text-4xl leading-tight font-medium">
        Connect your business channels
      </h1>
      <p className="mt-4 max-w-2xl text-base leading-7">
        VIGIE can monitor the conversations your business already uses and surface the commitments, requests and risks
        that need your attention.
      </p>
      {connectionIssue ? (
        <p className="mt-4 text-sm text-[var(--muted)]" role="status">
          {connectionFailureHeadline(connectionIssue.provider)}
        </p>
      ) : null}

      <div className="mt-8 grid gap-4">
        <section className="border border-[var(--line)] bg-[var(--panel)] px-5 py-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h2 className="text-lg font-semibold">Demo WhatsApp</h2>
            <p className="text-[11px] font-semibold tracking-[0.14em] uppercase">
              {demoEnabled ? "Prototype" : "Not configured"}
            </p>
          </div>
          <p className="mt-2 max-w-xl text-sm leading-6 text-[var(--muted)]">
            A practice inbox for demonstrations. It is not a live WhatsApp account.
          </p>
          {connected ? (
            <p className="mt-4 text-sm font-medium">Demo connection active</p>
          ) : (
            <button
              type="button"
              disabled={!demoEnabled}
              onClick={() => void connectDemo()}
              className="mt-4 border border-[var(--ink)] bg-[var(--panel)] px-3 py-2 text-sm font-medium text-[var(--ink)] disabled:opacity-50"
            >
              Demo connection
            </button>
          )}
          {connected ? <p className="mt-1 text-sm text-[var(--muted)]">Messages can now be imported into VIGIE.</p> : null}
          {!demoEnabled ? (
            <p className="mt-3 text-sm text-[var(--muted)]">The demo is turned off for this workspace.</p>
          ) : null}
        </section>

        {realChannels.map((channel) => {
          const view = integrationView(channel, busy, issueFor(channel.provider));
          return (
            <section key={channel.provider} className="border border-[var(--line)] bg-[var(--panel)] px-5 py-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <h2 className="text-lg font-semibold">{channel.label}</h2>
                <p className={badgeClass(view.tone)}>{view.badge}</p>
              </div>
              <p className="mt-2 max-w-xl text-sm leading-6 text-[var(--muted)]">{channel.description}</p>
              <p className="mt-3 text-sm leading-6 text-[var(--muted)]" role={view.phase === "needs_attention" ? "alert" : undefined}>
                {view.summary}
              </p>
              {view.resource ? (
                <p className="mt-3 text-sm">
                  {view.resource.label}:<span className="mt-1 block">{view.resource.value}</span>
                </p>
              ) : null}
              {view.activity ? <p className="mt-2 text-sm text-[var(--muted)]">{view.activity}</p> : null}
              {view.listening ? <p className="mt-2 text-sm">{view.listening}</p> : null}
              {view.lastReceived ? <p className="mt-1 text-sm text-[var(--muted)]">{view.lastReceived}</p> : null}
              {view.webhook ? <p className="mt-2 break-all text-sm font-medium text-[var(--ink)]">{view.webhook}</p> : null}
              {view.webhookMissing ? (
                <p className="mt-2 text-sm text-[var(--muted)]">The callback address is not available yet.</p>
              ) : null}
              {view.notice ? (
                <p className="mt-3 text-sm text-[var(--high)]" role="alert">
                  {view.notice}
                </p>
              ) : null}
              {!canManage ? (
                <p className="mt-4 text-sm text-[var(--muted)]">You do not have permission to manage integrations.</p>
              ) : (
                <IntegrationActions
                  channel={channel}
                  view={view}
                  phoneNumberId={phoneNumberId}
                  onPhoneNumberId={setPhoneNumberId}
                  onConnect={() => void connectChannel(channel)}
                  onSync={() =>
                    void runChannelAction(
                      channel.provider,
                      onSync ? () => onSync(channel.provider) : undefined,
                      channel.provider === "microsoft365"
                        ? "VIGIE couldn't sync Outlook. Try again."
                        : "VIGIE couldn't sync Gmail. Try again.",
                      "sync",
                    )
                  }
                  onListen={() =>
                    void runChannelAction(
                      channel.provider,
                      onEnableListening ? () => onEnableListening(channel.provider) : undefined,
                      "Automatic updates could not be turned on. Try again.",
                      "listen",
                      "Automatic updates are not set up. Sync now still imports mail.",
                    )
                  }
                  onDisconnect={() => void disconnectChannel(channel)}
                />
              )}
            </section>
          );
        })}
      </div>
      {connected ? (
        <form onSubmit={(event) => void submit(event)} className="mt-8 border border-[var(--line)] bg-[var(--panel)] px-5 py-5">
          <h2 className="text-lg font-semibold">Send a test WhatsApp message</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">Demo WhatsApp · Prototype</p>
          <label className="mt-5 block text-sm" htmlFor="demo-customer">
            Customer
          </label>
          <input
            id="demo-customer"
            value={customerName}
            onChange={(event) => setCustomerName(event.target.value)}
            className="mt-2 w-full border border-[var(--line)] bg-[var(--paper)] px-3 py-2 text-sm text-[var(--ink)]"
          />
          <label className="mt-4 block text-sm" htmlFor="demo-message">
            Message
          </label>
          <textarea
            id="demo-message"
            value={text}
            rows={3}
            onChange={(event) => setText(event.target.value)}
            className="mt-2 w-full border border-[var(--line)] bg-[var(--paper)] px-3 py-2 text-sm text-[var(--ink)]"
          />
          <button
            type="submit"
            disabled={phase === "pending"}
            className="mt-4 border border-[var(--ink)] bg-[var(--ink)] px-4 py-2 text-sm font-medium text-[var(--paper)] disabled:opacity-60"
          >
            Send to VIGIE
          </button>
          {notice ? (
            <p className="mt-4 text-sm" role={phase === "error" ? "alert" : "status"}>
              {notice}
            </p>
          ) : null}
        </form>
      ) : null}

      {connected ? (
        <section className="mt-8" aria-labelledby="recent-demo">
          <h2 id="recent-demo" className="text-lg font-semibold">
            Recent conversations
          </h2>
          {messages.length === 0 ? (
            <p className="mt-3 text-sm text-[var(--muted)]">
              No demo messages yet. Send one to see how VIGIE reads a conversation.
            </p>
          ) : (
            <ol className="mt-3 divide-y divide-[var(--line)] border-y border-[var(--line)]">
              {messages.map((message) => (
                <li key={message.message_id} className="py-4">
                  <p className="text-xs tracking-[0.14em] text-[var(--muted)] uppercase">
                    {message.source_label}
                    {message.connection ? ` · ${message.connection}` : ""}
                  </p>
                  <p className="mt-2 text-sm font-medium">{message.customer_name}</p>
                  <p className="mt-1 text-sm break-words text-[var(--muted)]">&ldquo;{message.text}&rdquo;</p>
                  <p className="mt-2 text-sm">{understanding(message.events)}</p>
                </li>
              ))}
            </ol>
          )}
        </section>
      ) : null}
    </article>
  );
}

function badgeClass(tone: IntegrationView["tone"]): string {
  const base = "text-[11px] font-semibold tracking-[0.14em] uppercase";
  if (tone === "attention") return `${base} text-[var(--high)]`;
  if (tone === "muted") return `${base} text-[var(--muted)]`;
  return base;
}

function IntegrationActions({
  channel,
  view,
  phoneNumberId,
  onPhoneNumberId,
  onConnect,
  onSync,
  onListen,
  onDisconnect,
}: {
  channel: ChannelStatus;
  view: IntegrationView;
  phoneNumberId: string;
  onPhoneNumberId: (value: string) => void;
  onConnect: () => void;
  onSync: () => void;
  onListen: () => void;
  onDisconnect: () => void;
}) {
  if (!view.showPhoneField && !view.primary && !view.sync && !view.listen && !view.disconnect) {
    return null;
  }
  const buttonClass =
    "border border-[var(--ink)] bg-[var(--panel)] px-3 py-2 text-sm font-medium text-[var(--ink)] disabled:opacity-50";
  return (
    <div className="mt-4">
      {view.showPhoneField ? (
        <>
          <label className="block text-sm" htmlFor={`whatsapp-phone-number-${channel.provider}`}>
            Phone number ID
          </label>
          <input
            id={`whatsapp-phone-number-${channel.provider}`}
            value={phoneNumberId}
            onChange={(event) => onPhoneNumberId(event.target.value)}
            className="mt-2 w-full border border-[var(--line)] bg-[var(--paper)] px-3 py-2 text-sm text-[var(--ink)]"
          />
        </>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2">
        {view.sync ? (
          <button type="button" onClick={onSync} className={buttonClass}>
            Sync now
          </button>
        ) : null}
        {view.listen ? (
          <button type="button" onClick={onListen} className={buttonClass}>
            Turn on automatic updates
          </button>
        ) : null}
        {view.primary ? (
          <button type="button" onClick={onConnect} className={buttonClass}>
            {view.primary.label}
          </button>
        ) : null}
        {view.disconnect ? (
          <button type="button" onClick={onDisconnect} className={buttonClass}>
            Disconnect
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function readDemoConnection(): boolean {
  return window.localStorage.getItem(CONNECTION_KEY) === "active";
}
