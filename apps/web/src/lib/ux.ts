import type { ChannelAvailability, ChannelStatus } from "@/lib/api/integrations";

const KNOWN_ERRORS: Record<string, string> = {
  "Configuration required.": "This channel is not set up yet.",
  "Invalid or expired connection attempt.": "Your connection session expired. Try connecting again.",
  "The provider could not complete the connection.": "The connection could not be completed. Try again.",
  "Gmail needs to be reconnected.": "Reconnect your Google account.",
  "Microsoft 365 needs to be reconnected.": "Reconnect your Microsoft account.",
  "VIGIE could not sync Gmail.": "VIGIE couldn't sync Gmail. Try again.",
  "VIGIE could not sync Microsoft 365.": "VIGIE couldn't sync Outlook. Try again.",
  "Real-time listening could not be renewed.": "Automatic updates need attention. Sync now still imports mail.",
  "Real-time listening is not configured.": "Automatic updates are not set up. Sync now still imports mail.",
  "Real-time listening could not be enabled.": "Automatic updates could not be turned on. Try again.",
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
  if (channel.availability !== "connected" || !channel.accountLabel) {
    return null;
  }
  if (channel.provider === "gmail") {
    return { label: "Gmail mailbox", value: channel.accountLabel };
  }
  if (channel.provider === "microsoft365") {
    return { label: "Outlook mailbox", value: channel.accountLabel };
  }
  if (channel.provider === "whatsapp") {
    return { label: "WhatsApp number", value: channel.accountLabel };
  }
  return { label: "Account", value: channel.accountLabel };
}

export function userFacingError(message: string): string {
  return KNOWN_ERRORS[message] ?? message;
}
