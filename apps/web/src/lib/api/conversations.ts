import { isRecord, requiredNumber, requiredString } from "@/lib/api/client";

export type ConversationPreview = {
  conversation_id: string;
  customer_id: string | null;
  customer_name: string;
  last_message: string;
  last_message_at: string;
  sender_type: string;
  direction: string;
};

export type ConversationBrief = {
  id: string;
  channel: string;
  message_count: number;
};

export function parseConversationPreview(value: unknown): ConversationPreview {
  if (!isRecord(value)) {
    throw new Error("Expected a conversation");
  }
  const customerId = value.customer_id;
  return {
    conversation_id: requiredString(value, "conversation_id"),
    customer_id: typeof customerId === "string" ? customerId : null,
    customer_name: requiredString(value, "customer_name"),
    last_message: typeof value.last_message === "string" ? value.last_message || "No message text" : requiredString(value, "last_message"),
    last_message_at: requiredString(value, "last_message_at"),
    sender_type: requiredString(value, "sender_type"),
    direction: requiredString(value, "direction"),
  };
}

export function parseConversationBrief(value: unknown): ConversationBrief | null {
  if (value === null) {
    return null;
  }
  if (!isRecord(value)) {
    throw new Error("Expected a conversation");
  }
  return {
    id: requiredString(value, "id"),
    channel: requiredString(value, "channel"),
    message_count: requiredNumber(value, "message_count"),
  };
}
