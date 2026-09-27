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
    return "No business event detected";
  }
  return "Conversation interpreted";
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
