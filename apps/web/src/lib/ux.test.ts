/// <reference types="vitest/globals" />
import type { ChannelStatus } from "@/lib/api/integrations";
import { connectionFailureDetail, integrationView } from "@/lib/ux";

const providers = [
  ["gmail", "Google"],
  ["microsoft365", "Microsoft"],
  ["whatsapp", "WhatsApp"],
] as const;

function channel(overrides: Partial<ChannelStatus>): ChannelStatus {
  return {
    provider: "gmail",
    label: "Google Workspace",
    description: "Analyze business email conversations.",
    availability: "not_configured",
    accountLabel: null,
    lastSyncAt: null,
    lastError: null,
    configured: false,
    ...overrides,
  };
}

describe("integration state", () => {
  it.each(providers)("keeps %s not configured free of sync and disconnect", (provider, name) => {
    const view = integrationView(channel({ provider, availability: "not_configured", configured: false, accountLabel: "old@example.com" }));

    expect(view.phase).toBe("not_configured");
    expect(view.badge).toBe("Not configured");
    expect(view.primary).toEqual({ label: `Configure ${name}`, kind: "configure" });
    expect(view.sync).toBe(false);
    expect(view.disconnect).toBe(false);
    expect(view.listen).toBe(false);
    expect(view.resource).toBeNull();
    expect(view.summary.toLowerCase()).not.toContain("not set up yet");
  });

  it.each(providers)("keeps %s ready to connect without a previous account", (provider, name) => {
    const view = integrationView(
      channel({
        provider,
        availability: "disconnected",
        configured: true,
        accountLabel: "old@example.com",
      }),
    );

    expect(view.phase).toBe("ready");
    expect(view.badge).toBe("Ready to connect");
    expect(view.primary).toEqual({ label: `Connect ${name}`, kind: "connect" });
    expect(view.sync).toBe(false);
    expect(view.disconnect).toBe(false);
    expect(view.resource).toBeNull();
    expect(view.summary.toLowerCase()).not.toContain("reconnect");
  });

  it("treats a pending connection as connecting", () => {
    const view = integrationView(channel({ availability: "pending", configured: true }));

    expect(view.phase).toBe("connecting");
    expect(view.badge).toBe("Connecting");
    expect(view.primary).toBeNull();
    expect(view.sync).toBe(false);
    expect(view.disconnect).toBe(false);
  });

  it.each(providers)("hides a duplicate connect action while %s is connecting", (provider) => {
    const view = integrationView(channel({ provider, availability: "available", configured: true }), {
      provider,
      action: "connect",
    });

    expect(view.phase).toBe("connecting");
    expect(view.badge).toBe("Connecting");
    expect(view.primary).toBeNull();
    expect(view.sync).toBe(false);
    expect(view.disconnect).toBe(false);
    expect(view.summary).toMatch(/Connecting/);
  });

  it("shows a connected mailbox with sync for Gmail and Outlook only", () => {
    const gmail = integrationView(
      channel({ provider: "gmail", availability: "connected", configured: true, accountLabel: "ada@example.com", realtime: "manual" }),
    );
    const microsoft = integrationView(
      channel({ provider: "microsoft365", availability: "connected", configured: true, accountLabel: "ada@example.com" }),
    );
    const whatsapp = integrationView(
      channel({ provider: "whatsapp", availability: "connected", configured: true, accountLabel: "+2348000000000" }),
    );

    expect(gmail.badge).toBe("Connected");
    expect(gmail.resource).toEqual({ label: "Connected Gmail mailbox", value: "ada@example.com" });
    expect(gmail.sync).toBe(true);
    expect(gmail.disconnect).toBe(true);
    expect(gmail.listen).toBe(true);
    expect(gmail.summary).toBe("VIGIE imports messages for analysis. VIGIE does not send email.");

    expect(microsoft.sync).toBe(true);
    expect(microsoft.listen).toBe(true);
    expect(microsoft.resource?.label).toBe("Connected Outlook mailbox");

    expect(whatsapp.sync).toBe(false);
    expect(whatsapp.listen).toBe(false);
    expect(whatsapp.disconnect).toBe(true);
    expect(whatsapp.resource).toEqual({ label: "Connected WhatsApp number", value: "+2348000000000" });
    expect(whatsapp.summary).toBe("VIGIE receives messages for analysis. VIGIE does not send a reply.");
  });

  it("hides Sync now while a sync is already running", () => {
    const view = integrationView(
      channel({ provider: "gmail", availability: "connected", configured: true, accountLabel: "ada@example.com" }),
      { provider: "gmail", action: "sync" },
    );

    expect(view.phase).toBe("syncing");
    expect(view.badge).toBe("Syncing");
    expect(view.sync).toBe(false);
    expect(view.primary).toBeNull();
    expect(view.disconnect).toBe(false);
    expect(view.summary).toBe("Importing new messages...");
    expect(view.resource?.value).toBe("ada@example.com");
  });

  it.each(providers)("treats a previously connected %s as needing attention", (provider, name) => {
    const view = integrationView(
      channel({
        provider,
        availability: "error",
        configured: false,
        accountLabel: "ada@example.com",
        lastSyncAt: "2026-09-28T12:00:00Z",
        lastError: "Configuration required.",
        realtime: provider === "gmail" ? "needs_attention" : undefined,
      }),
    );

    expect(view.phase).toBe("needs_attention");
    expect(view.badge).toBe("Needs attention");
    expect(view.resource?.value).toBe("ada@example.com");
    expect(view.activity).toBe("Last successful sync: 28 Sept 2026");
    expect(view.primary).toEqual({ label: `Reconnect ${name}`, kind: "reconnect" });
    expect(view.sync).toBe(false);
    expect(view.disconnect).toBe(true);
    expect(view.summary.toLowerCase()).not.toContain("not configured");
    expect(view.summary).not.toContain("This channel is not set up yet");
    expect(view.notice).toBeNull();
    if (provider === "gmail") {
      expect(view.listening).toBe("Automatic updates are paused until you reconnect.");
    }
  });

  it("keeps a usable Gmail mailbox connected when only automatic updates need attention", () => {
    const view = integrationView(
      channel({
        provider: "gmail",
        availability: "connected",
        configured: true,
        accountLabel: "ada@example.com",
        listening: false,
        realtime: "needs_attention",
      }),
    );

    expect(view.phase).toBe("connected");
    expect(view.sync).toBe(true);
    expect(view.listening).toBe("Automatic updates are paused. Sync now still imports mail.");
  });

  it("removes conflicting actions while disconnecting", () => {
    const view = integrationView(
      channel({ provider: "microsoft365", availability: "connected", configured: true, accountLabel: "ada@example.com" }),
      { provider: "microsoft365", action: "disconnect" },
    );

    expect(view.phase).toBe("disconnecting");
    expect(view.badge).toBe("Disconnecting");
    expect(view.summary).toBe("Removing this connection...");
    expect(view.primary).toBeNull();
    expect(view.sync).toBe(false);
    expect(view.disconnect).toBe(false);
  });

  it.each(providers)("keeps a failed first %s connection on that provider", (provider, name) => {
    const detail = connectionFailureDetail(provider);
    const issue = { provider, detail, connection: true as const };
    const failed = integrationView(
      channel({ provider, availability: "available", configured: true, accountLabel: "leaked@example.com" }),
      null,
      issue,
    );
    const other = integrationView(
      channel({
        provider: provider === "gmail" ? "microsoft365" : "gmail",
        availability: "available",
        configured: true,
      }),
      null,
      issue,
    );

    expect(failed.phase).toBe("ready");
    expect(failed.badge).toBe("Ready to connect");
    expect(failed.notice).toBe(detail);
    expect(failed.summary).not.toBe(detail);
    expect(failed.primary).toEqual({ label: `Connect ${name}`, kind: "connect" });
    expect(failed.resource).toBeNull();
    expect(failed.sync).toBe(false);
    expect(failed.disconnect).toBe(false);
    expect(other.notice).toBeNull();
    expect(other.phase).toBe("ready");
  });

  it.each(providers)("keeps a failed %s reconnect on the saved account", (provider, name) => {
    const detail = connectionFailureDetail(provider);
    const view = integrationView(
      channel({
        provider,
        availability: "error",
        configured: true,
        accountLabel: provider === "whatsapp" ? "+2348000000000" : "ada@example.com",
      }),
      null,
      { provider, detail, connection: true },
    );

    expect(view.phase).toBe("needs_attention");
    expect(view.notice).toBe(detail);
    expect(view.summary).not.toBe(detail);
    expect(view.primary).toEqual({ label: `Reconnect ${name}`, kind: "reconnect" });
    expect(view.resource?.value).toBe(provider === "whatsapp" ? "+2348000000000" : "ada@example.com");
    expect(view.sync).toBe(false);
    expect(view.disconnect).toBe(true);
  });

  it("maps a Microsoft permission failure without leaving the card", () => {
    const detail = connectionFailureDetail("microsoft365", "permissions");
    const view = integrationView(
      channel({ provider: "microsoft365", availability: "available", configured: true }),
      null,
      { provider: "microsoft365", detail, connection: true },
    );

    expect(detail).toBe("Microsoft permissions were not granted.");
    expect(view.badge).toBe("Ready to connect");
    expect(view.notice).toBe(detail);
    expect(view.primary).toEqual({ label: "Connect Microsoft", kind: "connect" });
  });

  it("does not treat a sync problem as a lost connection", () => {
    const view = integrationView(
      channel({ provider: "gmail", availability: "connected", configured: true, accountLabel: "ada@example.com" }),
      null,
      { provider: "gmail", detail: "VIGIE couldn't sync Gmail. Try again.", connection: false },
    );

    expect(view.phase).toBe("connected");
    expect(view.sync).toBe(true);
    expect(view.notice).toBe("VIGIE couldn't sync Gmail. Try again.");
    expect(view.summary).toBe("VIGIE imports messages for analysis. VIGIE does not send email.");
  });
});
