import { apiGet, apiPost, isRecord, requiredString } from "@/lib/api/client";

export const DEMO_MESSAGE_TIME = "2026-09-24T09:00:00+01:00";

export type DemoInboundResult = {
  created: boolean;
  analyzed: boolean;
  message_id: string;
  source: string;
  source_label: string;
  connection: string | null;
  customer_name: string;
  text: string;
  occurred_at: string;
  external_message_id: string;
  events: string[];
};

export type DemoConversation = {
  message_id: string;
  customer_name: string;
  text: string;
  occurred_at: string;
  source_label: string;
  connection: string | null;
  events: string[];
};

export function sendDemoMessage(input: {
  businessId: string;
  customerName: string;
  text: string;
  externalMessageId: string;
  conversationId: string;
}): Promise<DemoInboundResult> {
  return apiPost(
    "/api/integrations/demo/messages",
    {
      business_id: input.businessId,
      customer_name: input.customerName,
      conversation_id: input.conversationId,
      external_message_id: input.externalMessageId,
      text: input.text,
      timestamp: DEMO_MESSAGE_TIME,
    },
    parseDemoResult,
  );
}

export function loadDemoMessages(businessId: string): Promise<DemoConversation[]> {
  return apiGet(`/api/integrations/demo/messages?business_id=${businessId}`, parseDemoList);
}

export function understanding(events: string[]): string {
  if (events.includes("PAYMENT_COMMITMENT")) {
    return "Payment commitment detected";
  }
  if (events.includes("PAYMENT_CLAIM")) {
    return "Payment claim detected";
  }
  if (events.includes("UNANSWERED_REQUEST")) {
    return "Customer request detected";
  }
  if (events.length === 0) {
    return "Nothing that needs attention";
  }
  return "Conversation read";
}

function parseDemoResult(value: unknown): DemoInboundResult {
  if (!isRecord(value) || !Array.isArray(value.events)) {
    throw new Error("Expected a demo message");
  }
  return {
    created: value.created === true,
    analyzed: value.analyzed === true,
    message_id: requiredString(value, "message_id"),
    source: requiredString(value, "source"),
    source_label: requiredString(value, "source_label"),
    connection: typeof value.connection === "string" ? value.connection : null,
    customer_name: requiredString(value, "customer_name"),
    text: requiredString(value, "text"),
    occurred_at: requiredString(value, "occurred_at"),
    external_message_id: requiredString(value, "external_message_id"),
    events: value.events.filter((item): item is string => typeof item === "string"),
  };
}

export type ChannelAvailability =
  | "not_configured"
  | "available"
  | "prototype"
  | "pending"
  | "connected"
  | "disconnected"
  | "error";

export type GmailRealtime = "listening" | "manual" | "needs_attention" | "not_configured";

export type ChannelStatus = {
  provider: string;
  label: string;
  description: string;
  availability: ChannelAvailability;
  accountLabel: string | null;
  lastSyncAt: string | null;
  lastError: string | null;
  configured: boolean;
  listening?: boolean;
  realtime?: GmailRealtime;
  lastNotificationAt?: string | null;
  pubsubConfigured?: boolean;
  webhookUrl?: string | null;
};

export function loadChannels(businessId: string): Promise<ChannelStatus[]> {
  return apiGet(`/api/integrations?business_id=${businessId}`, parseChannels);
}

export function connectWhatsapp(businessId: string, phoneNumberId: string): Promise<ChannelStatus> {
  return apiPost(
    "/api/integrations/whatsapp/connect",
    { business_id: businessId, phone_number_id: phoneNumberId },
    parseChannel,
  );
}

export function disconnectChannel(businessId: string, provider: string): Promise<ChannelStatus> {
  return apiPost(`/api/integrations/${provider}/disconnect`, { business_id: businessId }, parseChannel);
}

export function syncGmail(businessId: string): Promise<void> {
  return apiPost(`/api/integrations/gmail/sync?business_id=${encodeURIComponent(businessId)}`, {}, () => undefined);
}

export function syncMicrosoft(businessId: string): Promise<void> {
  return apiPost(`/api/integrations/microsoft/sync?business_id=${encodeURIComponent(businessId)}`, {}, () => undefined);
}

export function enableGmailListening(businessId: string): Promise<ChannelStatus> {
  return apiPost(
    `/api/integrations/gmail/watch?business_id=${encodeURIComponent(businessId)}`,
    {},
    parseChannel,
  );
}

export function oauthConnectPath(provider: string, businessId: string): string {
  const route = provider === "microsoft365" ? "microsoft" : provider;
  return `/api/integrations/${route}/connect?business_id=${businessId}`;
}

function parseDemoList(value: unknown): DemoConversation[] {
  if (!Array.isArray(value)) {
    throw new Error("Expected demo messages");
  }
  return value.map((item) => {
    if (!isRecord(item) || !Array.isArray(item.events)) {
      throw new Error("Expected a demo message");
    }
    return {
      message_id: requiredString(item, "message_id"),
      customer_name: requiredString(item, "customer_name"),
      text: requiredString(item, "text"),
      occurred_at: requiredString(item, "occurred_at"),
      source_label: requiredString(item, "source_label"),
      connection: typeof item.connection === "string" ? item.connection : null,
      events: item.events.filter((event): event is string => typeof event === "string"),
    };
  });
}

function parseChannels(value: unknown): ChannelStatus[] {
  if (!Array.isArray(value)) {
    throw new Error("Expected channels");
  }
  return value.map(parseChannel);
}

function parseChannel(value: unknown): ChannelStatus {
  if (!isRecord(value)) {
    throw new Error("Expected a channel");
  }
  const availability = requiredString(value, "availability");
  return {
    provider: requiredString(value, "provider"),
    label: requiredString(value, "label"),
    description: requiredString(value, "description"),
    availability: availability as ChannelAvailability,
    accountLabel: typeof value.account_label === "string" ? value.account_label : null,
    lastSyncAt: typeof value.last_sync_at === "string" ? value.last_sync_at : null,
    lastError: typeof value.last_error === "string" ? value.last_error : null,
    configured: value.configured === true,
    listening: value.listening === true,
    realtime: realtimeValue(value.realtime),
    lastNotificationAt: typeof value.last_notification_at === "string" ? value.last_notification_at : null,
    pubsubConfigured: value.pubsub_configured === true,
    webhookUrl: typeof value.webhook_url === "string" && value.webhook_url.length > 0 ? value.webhook_url : null,
  };
}

function realtimeValue(value: unknown): GmailRealtime {
  if (value === "listening" || value === "manual" || value === "needs_attention" || value === "not_configured") {
    return value;
  }
  return "not_configured";
}
