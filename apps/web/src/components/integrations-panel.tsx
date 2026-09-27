"use client";

import { useState, type FormEvent } from "react";

import { ApiError } from "@/lib/api/client";
import {
  understanding,
  type ChannelStatus,
  type DemoConversation,
  type DemoInboundResult,
} from "@/lib/api/integrations";
import { formatDate, relativeTime } from "@/lib/format";

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

const STATUS_LABEL: Record<ChannelStatus["availability"], string> = {
  not_configured: "Not configured",
  available: "Available",
  prototype: "Prototype",
  pending: "Pending",
  connected: "Connected",
  disconnected: "Disconnected",
  error: "Error",
};

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
}) {
  const [connected, setConnected] = useState(initiallyConnected && demoEnabled);
  const [customerName, setCustomerName] = useState("Amaka Bello");
  const [text, setText] = useState("I'll pay the remaining ₦150,000 on Friday.");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [messages, setMessages] = useState(recent);
  const [phase, setPhase] = useState<"idle" | "pending" | "sent" | "error">("idle");
  const [notice, setNotice] = useState<string | null>(null);
  const [channelNotice, setChannelNotice] = useState<string | null>(null);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);

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
      setNotice("Message received. VIGIE is analyzing the conversation.");
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
          : "VIGIE couldn't receive that message. Please try again.",
      );
    }
  }

  async function connectChannel(channel: ChannelStatus) {
    if (!channel.configured) {
      setChannelNotice("Configuration required.");
      return;
    }
    if (channel.provider === "whatsapp") {
      if (!phoneNumberId.trim()) {
        setChannelNotice("Enter the WhatsApp phone number ID.");
        return;
      }
      if (!onConnectWhatsapp) {
        setChannelNotice("Configuration required.");
        return;
      }
      setBusyProvider(channel.provider);
      setChannelNotice(null);
      try {
        await onConnectWhatsapp(phoneNumberId.trim());
        setChannelNotice(null);
      } catch (error) {
        setChannelNotice(
          error instanceof ApiError && error.status === 409
            ? "Configuration required."
            : "VIGIE couldn't connect that channel. Please try again.",
        );
      } finally {
        setBusyProvider(null);
      }
      return;
    }
    if (!onStartOauth) {
      setChannelNotice("Configuration required.");
      return;
    }
    onStartOauth(channel.provider);
  }

  async function runChannelAction(
    provider: string,
    action: (() => Promise<void>) | undefined,
    failure: string,
    unconfigured?: string,
  ) {
    if (!action) {
      return;
    }
    setBusyProvider(provider);
    setChannelNotice(null);
    try {
      await action();
    } catch (error) {
      setChannelNotice(error instanceof ApiError && error.status === 409 && unconfigured ? unconfigured : failure);
    } finally {
      setBusyProvider(null);
    }
  }

  async function disconnectChannel(channel: ChannelStatus) {
    if (!onDisconnect) {
      return;
    }
    setBusyProvider(channel.provider);
    setChannelNotice(null);
    try {
      await onDisconnect(channel.provider);
    } catch {
      setChannelNotice("VIGIE couldn't disconnect that channel. Please try again.");
    } finally {
      setBusyProvider(null);
    }
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

      <div className="mt-8 grid gap-4">
        <section className="border border-[var(--line)] bg-[var(--panel)] px-5 py-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h2 className="text-lg font-semibold">Demo WhatsApp</h2>
            <p className="text-[11px] font-semibold tracking-[0.14em] uppercase">
              {demoEnabled ? "Prototype" : "Not configured"}
            </p>
          </div>
          <p className="mt-2 max-w-xl text-sm leading-6 text-[var(--muted)]">
            A simulated WhatsApp Business connector for local development. It is not a live WhatsApp account.
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
          {!demoEnabled ? <p className="mt-3 text-sm text-[var(--muted)]">Available when demo mode is on.</p> : null}
        </section>

        {realChannels.map((channel) => (
          <section key={channel.provider} className="border border-[var(--line)] bg-[var(--panel)] px-5 py-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <h2 className="text-lg font-semibold">{channel.label}</h2>
              <p className="text-[11px] font-semibold tracking-[0.14em] uppercase">{STATUS_LABEL[channel.availability]}</p>
            </div>
            <p className="mt-2 max-w-xl text-sm leading-6 text-[var(--muted)]">{channel.description}</p>
            <WhatsAppSetup channel={channel} />
            <GmailSetup channel={channel} />
            {channel.accountLabel ? <p className="mt-3 text-sm">Account {channel.accountLabel}</p> : null}
            <GmailRealtimeStatus channel={channel} />
            <p className="mt-2 text-sm text-[var(--muted)]">
              {channel.lastSyncAt ? `Last activity ${formatDate(channel.lastSyncAt, "UTC")}` : "No activity yet"}
            </p>
            {(channel.availability === "error" || channel.realtime === "needs_attention") && channel.lastError ? (
              <p className="mt-3 text-sm text-[var(--high)]" role="alert">
                {channel.lastError}
              </p>
            ) : null}
            {!canManage ? (
              <p className="mt-4 text-sm text-[var(--muted)]">You do not have permission to manage integrations.</p>
            ) : channel.availability === "connected" ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {channel.provider === "gmail" ? (
                  <>
                    <button
                      type="button"
                      disabled={busyProvider === channel.provider}
                      onClick={() =>
                        void runChannelAction(
                          channel.provider,
                          onSync ? () => onSync(channel.provider) : undefined,
                          "VIGIE couldn't sync Gmail. Please try again.",
                        )
                      }
                      className="border border-[var(--ink)] bg-[var(--panel)] px-3 py-2 text-sm font-medium text-[var(--ink)] disabled:opacity-50"
                    >
                      Sync now
                    </button>
                    {channel.listening ? null : (
                      <button
                        type="button"
                        disabled={busyProvider === channel.provider}
                        onClick={() =>
                          void runChannelAction(
                            channel.provider,
                            onEnableListening ? () => onEnableListening(channel.provider) : undefined,
                          "Real-time listening could not be enabled.",
                          "Real-time listening is not configured.",
                        )
                        }
                        className="border border-[var(--ink)] bg-[var(--panel)] px-3 py-2 text-sm font-medium text-[var(--ink)] disabled:opacity-50"
                      >
                        Enable real-time listening
                      </button>
                    )}
                  </>
                ) : null}
                <button
                  type="button"
                  disabled={busyProvider === channel.provider}
                  onClick={() => void disconnectChannel(channel)}
                  className="border border-[var(--ink)] bg-[var(--panel)] px-3 py-2 text-sm font-medium text-[var(--ink)] disabled:opacity-50"
                >
                  Disconnect
                </button>
              </div>
            ) : (
              <div className="mt-4">
                {channel.provider === "whatsapp" && channel.configured ? (
                  <>
                    <label className="block text-sm" htmlFor="whatsapp-phone-number">
                      Phone number ID
                    </label>
                    <input
                      id="whatsapp-phone-number"
                      value={phoneNumberId}
                      onChange={(event) => setPhoneNumberId(event.target.value)}
                      className="mt-2 w-full border border-[var(--line)] bg-[var(--paper)] px-3 py-2 text-sm text-[var(--ink)]"
                    />
                  </>
                ) : null}
                <button
                  type="button"
                  disabled={busyProvider === channel.provider}
                  onClick={() => void connectChannel(channel)}
                  className="mt-4 border border-[var(--ink)] bg-[var(--panel)] px-3 py-2 text-sm font-medium text-[var(--ink)] disabled:opacity-50"
                >
                  {connectLabel(channel)}
                </button>
              </div>
            )}
          </section>
        ))}
      </div>
      {channelNotice ? (
        <p className="mt-4 text-sm text-[var(--high)]" role="alert">
          {channelNotice}
        </p>
      ) : null}

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
            <p className="mt-3 text-sm text-[var(--muted)]">No demo messages yet.</p>
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

function WhatsAppSetup({ channel }: { channel: ChannelStatus }) {
  if (channel.provider !== "whatsapp") {
    return null;
  }
  if (!channel.configured) {
    return (
      <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
        Meta credentials are not set on the API. WhatsApp stays not configured until the app secret, verify token, and
        access token exist. That does not connect a number.
      </p>
    );
  }
  return (
    <div className="mt-3 text-sm leading-6 text-[var(--muted)]">
      <p>
        In the Meta app, set the callback to the webhook and subscribe to messages. Then enter the phone number ID from
        that WhatsApp Business account. VIGIE only receives messages. It does not send a reply.
      </p>
      {channel.webhookUrl ? (
        <p className="mt-2 break-all font-medium text-[var(--ink)]">{channel.webhookUrl}</p>
      ) : (
        <p className="mt-2">The public API origin is not set, so the callback URL cannot be shown yet.</p>
      )}
    </div>
  );
}

function GmailSetup({ channel }: { channel: ChannelStatus }) {
  if (channel.provider !== "gmail") {
    return null;
  }
  if (!channel.configured) {
    return (
      <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
        Google OAuth is not configured on the API. Gmail stays not configured until a client id, client secret, and
        redirect URI exist.
      </p>
    );
  }
  if (channel.availability === "connected") {
    return null;
  }
  return (
    <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
      Connect Google starts OAuth. Google returns the mailbox to the API. VIGIE stores that mailbox for this business
      and does not send email.
    </p>
  );
}

function GmailRealtimeStatus({ channel }: { channel: ChannelStatus }) {
  if (channel.provider !== "gmail" || channel.availability !== "connected") {
    return null;
  }
  return (
    <div className="mt-3 text-sm">
      {channel.listening ? <p>Listening for new messages</p> : null}
      {channel.realtime === "manual" ? <p>Manual sync available</p> : null}
      {channel.realtime === "manual" && !channel.pubsubConfigured ? <p>Real-time listening: Not configured</p> : null}
      {channel.realtime === "needs_attention" ? (
        <>
          <p>Needs attention</p>
          <p>The Gmail watch is not active.</p>
        </>
      ) : null}
      {channel.lastNotificationAt ? (
        <p className="text-[var(--muted)]">Last received: {relativeTime(channel.lastNotificationAt, new Date())}</p>
      ) : null}
    </div>
  );
}

function connectLabel(channel: ChannelStatus): string {
  if (channel.provider === "whatsapp") {
    return "Connect WhatsApp";
  }
  if (channel.provider === "gmail") {
    return channel.availability === "error" || channel.availability === "disconnected" ? "Reconnect" : "Connect Google";
  }
  if (channel.provider === "microsoft365") {
    return "Connect Microsoft";
  }
  return "Connect";
}

export function readDemoConnection(): boolean {
  return window.localStorage.getItem(CONNECTION_KEY) === "active";
}
