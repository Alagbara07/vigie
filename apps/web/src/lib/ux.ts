import type { ChannelAvailability, ChannelStatus } from "@/lib/api/integrations";
import { formatDate, relativeTime } from "@/lib/format";

const KNOWN_ERRORS: Record<string, string> = {
  "Invalid or expired connection attempt.": "Your connection session expired. Try connecting again.",
  "The provider could not complete the connection.": "The connection could not be completed. Try again.",
  "Gmail needs to be reconnected.": "Reconnect your Google account.",
  "Microsoft 365 needs to be reconnected.": "Reconnect your Microsoft account.",
  "VIGIE could not sync Gmail.": "VIGIE couldn't sync Gmail. Try again.",
  "VIGIE could not sync Microsoft 365.": "VIGIE couldn't sync Outlook. Try again.",
  "Real-time listening could not be renewed.": "Automatic updates are paused. Sync now still imports mail.",
  "Real-time listening is not configured.": "Automatic updates are not set up. Sync now still imports mail.",
  "Real-time listening could not be enabled.": "Automatic updates could not be turned on. Try again.",
};

export type IntegrationPhase =
  | "not_configured"
  | "ready"
  | "connecting"
  | "connected"
  | "syncing"
  | "disconnecting"
  | "needs_attention";

export type IntegrationBusy = {
  provider: string;
  action: "connect" | "sync" | "disconnect" | "listen";
} | null;

export type IntegrationIssue = {
  provider: string;
  detail: string;
  connection: boolean;
};

export type IntegrationView = {
  phase: IntegrationPhase;
  badge: string;
  tone: "muted" | "neutral" | "attention";
  summary: string;
  resource: { label: string; value: string } | null;
  activity: string | null;
  listening: string | null;
  lastReceived: string | null;
  notice: string | null;
  webhook: string | null;
  webhookMissing: boolean;
  showPhoneField: boolean;
  sync: boolean;
  listen: boolean;
  disconnect: boolean;
  primary: { label: string; kind: "configure" | "connect" | "reconnect" } | null;
};

export function channelStatusLabel(availability: ChannelAvailability): string {
  if (availability === "available" || availability === "disconnected") {
    return "Ready to connect";
  }
  if (availability === "pending") {
    return "Connecting";
  }
  if (availability === "error") {
    return "Needs attention";
  }
  if (availability === "connected") {
    return "Connected";
  }
  if (availability === "prototype") {
    return "Prototype";
  }
  return "Not configured";
}

export function channelStatusTone(availability: ChannelAvailability): "muted" | "neutral" | "attention" {
  if (availability === "error") {
    return "attention";
  }
  if (availability === "not_configured" || availability === "prototype") {
    return "muted";
  }
  return "neutral";
}

export function connectedAccount(channel: ChannelStatus): { label: string; value: string } | null {
  const phase = integrationPhase(channel, null);
  if (phase !== "connected" && phase !== "needs_attention") {
    return null;
  }
  return resourceLabel(channel);
}

export function userFacingError(message: string): string {
  return KNOWN_ERRORS[message] ?? message;
}

export function knownApiDetail(detail: string | null | undefined): string | null {
  if (!detail || !(detail in KNOWN_ERRORS)) {
    return null;
  }
  return KNOWN_ERRORS[detail];
}

const SUPPORTS_SYNC = new Set(["gmail", "microsoft365"]);

export function integrationPhase(channel: ChannelStatus, busy: IntegrationBusy): IntegrationPhase {
  if (busy?.provider === channel.provider) {
    if (busy.action === "sync" || busy.action === "listen") {
      return "syncing";
    }
    if (busy.action === "disconnect") {
      return "disconnecting";
    }
    return "connecting";
  }
  if (channel.availability === "error") {
    return "needs_attention";
  }
  if (channel.availability === "pending") {
    return "connecting";
  }
  if (channel.availability === "connected") {
    return "connected";
  }
  if (channel.availability === "not_configured" || channel.availability === "prototype") {
    return "not_configured";
  }
  return "ready";
}

export function connectionFailureHeadline(provider: string): string {
  if (provider === "gmail") return "Google Workspace couldn't be connected.";
  if (provider === "microsoft365") return "Microsoft 365 couldn't be connected.";
  if (provider === "whatsapp") return "WhatsApp couldn't be connected.";
  return "The connection could not be completed.";
}

export function connectionFailureDetail(provider: string): string {
  if (provider === "gmail") return "We couldn't connect your Google account. Please try again.";
  if (provider === "microsoft365") return "We couldn't connect your Microsoft 365 account. Please try again.";
  if (provider === "whatsapp") return "We couldn't connect WhatsApp. Check your configuration and try again.";
  return "We couldn't complete this connection. Please try again.";
}

export function integrationView(
  channel: ChannelStatus,
  busy: IntegrationBusy = null,
  issue: IntegrationIssue | null = null,
): IntegrationView {
  const stored = integrationPhase(channel, busy);
  const ownsIssue = issue?.provider === channel.provider;
  const connectionIssue = Boolean(ownsIssue && issue?.connection);
  const phase = connectionIssue && (stored === "ready" || stored === "not_configured") ? "needs_attention" : stored;
  const name = providerName(channel.provider);
  const active = busy?.provider === channel.provider ? busy.action : null;
  const showResource = stored === "connected" || stored === "needs_attention" || stored === "syncing" || stored === "disconnecting";
  return {
    phase,
    badge: phaseBadge(phase),
    tone: phase === "needs_attention" ? "attention" : phase === "not_configured" ? "muted" : "neutral",
    summary: connectionIssue ? issue!.detail : phaseSummary(channel, stored, active),
    resource: showResource ? resourceLabel(channel) : null,
    activity: activityLine(channel, stored),
    listening: listeningLine(channel, stored),
    lastReceived:
      stored === "connected" && channel.provider === "gmail" && channel.lastNotificationAt
        ? `Last received: ${relativeTime(channel.lastNotificationAt, new Date())}`
        : null,
    notice: noticeFor(channel, stored, issue),
    webhook: stored === "ready" && channel.provider === "whatsapp" ? channel.webhookUrl ?? null : null,
    webhookMissing: stored === "ready" && channel.provider === "whatsapp" && !channel.webhookUrl,
    showPhoneField: channel.provider === "whatsapp" && channel.configured && (stored === "ready" || stored === "needs_attention" || phase === "needs_attention"),
    sync: stored === "connected" && SUPPORTS_SYNC.has(channel.provider),
    listen: stored === "connected" && channel.provider === "gmail" && !channel.listening,
    disconnect: stored === "connected" || stored === "needs_attention",
    primary: primaryAction(stored, name),
  };
}

function noticeFor(channel: ChannelStatus, stored: IntegrationPhase, issue: IntegrationIssue | null): string | null {
  if (issue?.provider === channel.provider && !issue.connection) {
    return issue.detail;
  }
  if (stored === "connected") {
    return knownApiDetail(channel.lastError);
  }
  return null;
}

function phaseBadge(phase: IntegrationPhase): string {
  if (phase === "not_configured") return "Not configured";
  if (phase === "ready") return "Ready to connect";
  if (phase === "connecting") return "Connecting";
  if (phase === "connected") return "Connected";
  if (phase === "syncing") return "Syncing";
  if (phase === "disconnecting") return "Disconnecting";
  return "Needs attention";
}

function providerName(provider: string): string {
  if (provider === "gmail") return "Google";
  if (provider === "microsoft365") return "Microsoft";
  if (provider === "whatsapp") return "WhatsApp";
  return "integration";
}

function primaryAction(
  phase: IntegrationPhase,
  name: string,
): IntegrationView["primary"] {
  if (phase === "not_configured") return { label: `Configure ${name}`, kind: "configure" };
  if (phase === "ready") return { label: `Connect ${name}`, kind: "connect" };
  if (phase === "needs_attention") return { label: `Reconnect ${name}`, kind: "reconnect" };
  return null;
}

function phaseSummary(
  channel: ChannelStatus,
  phase: IntegrationPhase,
  action: "connect" | "sync" | "disconnect" | "listen" | null,
): string {
  if (phase === "not_configured") {
    if (channel.provider === "gmail") {
      return "Connect Google Workspace to let VIGIE analyze business email conversations.";
    }
    if (channel.provider === "microsoft365") {
      return "Connect Microsoft 365 to let VIGIE analyze Outlook conversations.";
    }
    if (channel.provider === "whatsapp") {
      return "Connect WhatsApp to let VIGIE analyze customer conversations.";
    }
    return "Connect this integration to let VIGIE analyze conversations.";
  }
  if (phase === "ready") {
    if (channel.provider === "gmail") {
      return "Connect Google Workspace to bring a Gmail mailbox into this business.";
    }
    if (channel.provider === "microsoft365") {
      return "Connect Microsoft 365 to bring an Outlook mailbox into this business.";
    }
    if (channel.provider === "whatsapp") {
      return "Connect WhatsApp to bring a business number into this business. VIGIE receives messages. It does not send a reply.";
    }
    return "Connect this integration to bring conversations into this business.";
  }
  if (phase === "needs_attention") {
    if (channel.provider === "gmail") {
      return "Your Google account needs to be reconnected before VIGIE can continue importing email.";
    }
    if (channel.provider === "microsoft365") {
      return "Your Microsoft account needs to be reconnected before VIGIE can continue importing email.";
    }
    if (channel.provider === "whatsapp") {
      return "Your WhatsApp number needs to be reconnected before VIGIE can continue receiving messages.";
    }
    return "This integration needs to be reconnected before VIGIE can continue.";
  }
  if (phase === "connecting") {
    if (channel.provider === "whatsapp") return "Connecting your WhatsApp number...";
    if (channel.provider === "microsoft365") return "Connecting your Microsoft account...";
    if (channel.provider === "gmail") return "Connecting your Google account...";
    return "Connecting your account...";
  }
  if (phase === "disconnecting") {
    return "Removing this connection...";
  }
  if (phase === "syncing") {
    return action === "listen" ? "Turning on automatic updates..." : "Importing new messages...";
  }
  if (channel.provider === "whatsapp") {
    return "VIGIE receives messages for analysis. VIGIE does not send a reply.";
  }
  return "VIGIE imports messages for analysis. VIGIE does not send email.";
}

function resourceLabel(channel: ChannelStatus): { label: string; value: string } | null {
  if (!channel.accountLabel) return null;
  if (channel.provider === "gmail") return { label: "Connected Gmail mailbox", value: channel.accountLabel };
  if (channel.provider === "microsoft365") return { label: "Connected Outlook mailbox", value: channel.accountLabel };
  if (channel.provider === "whatsapp") return { label: "Connected WhatsApp number", value: channel.accountLabel };
  return { label: "Connected account", value: channel.accountLabel };
}

function activityLine(channel: ChannelStatus, phase: IntegrationPhase): string | null {
  if ((phase === "connected" || phase === "syncing") && channel.lastSyncAt) {
    return `Last sync: ${formatDate(channel.lastSyncAt, "UTC")}`;
  }
  if (phase === "needs_attention" && channel.lastSyncAt) {
    return `Last successful sync: ${formatDate(channel.lastSyncAt, "UTC")}`;
  }
  if (phase === "connected") {
    return channel.provider === "whatsapp" ? "Waiting for messages." : "Nothing imported yet.";
  }
  return null;
}

function listeningLine(channel: ChannelStatus, phase: IntegrationPhase): string | null {
  if (channel.provider !== "gmail") return null;
  if (phase === "needs_attention" && channel.realtime === "needs_attention") {
    return "Automatic updates are paused until you reconnect.";
  }
  if (phase !== "connected") return null;
  if (channel.listening) return "Listening for new messages";
  if (channel.realtime === "needs_attention") {
    return "Automatic updates are paused. Sync now still imports mail.";
  }
  if (channel.realtime === "manual") return "New mail is imported when you sync.";
  return null;
}

