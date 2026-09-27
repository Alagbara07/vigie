"use client";

import { useState, type FormEvent } from "react";

import { ApiError } from "@/lib/api/client";
import {
  understanding,
  type DemoConversation,
  type DemoInboundResult,
} from "@/lib/api/integrations";

const CONNECTION_KEY = "vigie-demo-whatsapp";

type SendInput = {
  customerName: string;
  text: string;
};

export function IntegrationsPanel({
  demoEnabled,
  initiallyConnected = false,
  recent = [],
  onSend,
  onRefresh,
}: {
  demoEnabled: boolean;
  initiallyConnected?: boolean;
  recent?: DemoConversation[];
  onSend: (input: SendInput) => Promise<DemoInboundResult>;
  onRefresh?: () => Promise<DemoConversation[]>;
}) {
  const [connected, setConnected] = useState(initiallyConnected && demoEnabled);
  const [customerName, setCustomerName] = useState("Amaka Bello");
  const [text, setText] = useState("I'll pay the remaining ₦150,000 on Friday.");
  const [messages, setMessages] = useState(recent);
  const [phase, setPhase] = useState<"idle" | "pending" | "sent" | "error">("idle");
  const [notice, setNotice] = useState<string | null>(null);

  async function connect() {
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
            <h2 className="text-lg font-semibold">WhatsApp Business</h2>
            <p className="text-[11px] font-semibold tracking-[0.14em] uppercase">Prototype</p>
          </div>
          <p className="mt-2 max-w-xl text-sm leading-6 text-[var(--muted)]">
            Monitor customer conversations and identify commitments, payment claims and requests.
          </p>
          {connected ? (
            <p className="mt-4 text-sm font-medium">Demo connection active</p>
          ) : (
            <button
              type="button"
              disabled={!demoEnabled}
              onClick={() => void connect()}
              className="mt-4 border border-[var(--ink)] px-3 py-2 text-sm font-medium disabled:opacity-50"
            >
              Demo connection
            </button>
          )}
          {connected ? (
            <p className="mt-1 text-sm text-[var(--muted)]">Messages can now be imported into VIGIE.</p>
          ) : null}
          {!demoEnabled ? (
            <p className="mt-3 text-sm text-[var(--muted)]">Available when demo mode is on.</p>
          ) : null}
        </section>

        <ChannelSoon
          title="Google Workspace"
          detail="Analyze business email conversations."
        />
        <ChannelSoon title="Microsoft 365" detail="Analyze Outlook business conversations." />
      </div>

      {connected ? (
        <form onSubmit={(event) => void submit(event)} className="mt-8 border border-[var(--line)] bg-[var(--panel)] px-5 py-5">
          <h2 className="text-lg font-semibold">Send a test WhatsApp message</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">WhatsApp Business · Demo connection</p>
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

function ChannelSoon({ title, detail }: { title: string; detail: string }) {
  return (
    <section className="border border-[var(--line)] bg-[var(--panel)] px-5 py-5">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{detail}</p>
      <p className="mt-4 text-sm text-[var(--muted)]">Coming soon</p>
    </section>
  );
}

export function readDemoConnection(): boolean {
  return window.localStorage.getItem(CONNECTION_KEY) === "active";
}
