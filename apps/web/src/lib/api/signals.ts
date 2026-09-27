import { apiGet, isRecord, moneyValue, requiredString } from "@/lib/api/client";
import { parseConversationBrief, type ConversationBrief } from "@/lib/api/conversations";
import { parseCustomer, type CustomerBrief } from "@/lib/api/customers";

export type AttentionGroup = "risk" | "opportunity" | "operations";
export type SignalStatusFilter = "all" | "open" | "resolved";
export type SignalKindFilter = "all" | AttentionGroup;

export type ActionBrief = {
  id: string;
  action_type: string;
  title: string | null;
  description: string | null;
  status: string;
  proposed_content: string | null;
};

export type SignalRecord = {
  id: string;
  business_id: string;
  signal_type: string;
  category: string;
  severity: string;
  title: string;
  description: string;
  status: string;
  financial_impact_amount: string | null;
  currency: string | null;
  customer_name: string | null;
  attention_group: AttentionGroup;
  created_at: string;
  action: ActionBrief | null;
};

export type SignalDetail = SignalRecord & {
  timezone: string;
  customer: CustomerBrief | null;
  commitment: {
    id: string;
    commitment_type: string;
    status: string;
    amount: string | null;
    currency: string | null;
    due_at: string | null;
    due_text: string | null;
    description: string;
  } | null;
  event: {
    id: string;
    event_type: string;
    occurred_at: string;
    description: string | null;
  } | null;
  evidence: {
    message_id: string;
    content: string;
    sender_type: string;
    direction: string;
    occurred_at: string;
    source?: string | null;
    source_label?: string | null;
    connection?: string | null;
    external_message_id?: string | null;
  } | null;
  conversation: ConversationBrief | null;
};

export function loadSignals(businessId: string): Promise<SignalRecord[]> {
  return apiGet(`/api/signals?business_id=${businessId}`, parseSignalList);
}

export function loadSignalDetail(signalId: string, businessId: string): Promise<SignalDetail> {
  return apiGet(`/api/signals/${signalId}?business_id=${businessId}`, parseSignalDetail);
}

export function signalHref(signalId: string, businessId: string): string {
  return `/signals/${signalId}?business_id=${businessId}`;
}

export function parseSignalList(value: unknown): SignalRecord[] {
  if (!Array.isArray(value)) {
    throw new Error("Expected a signal list");
  }
  return value.map(parseSignal);
}

function parseSignal(value: unknown): SignalRecord {
  if (!isRecord(value)) {
    throw new Error("Expected a signal");
  }
  const impact = value.financial_impact_amount;
  const currency = value.currency;
  const customerName = value.customer_name;
  return {
    id: requiredString(value, "id"),
    business_id: requiredString(value, "business_id"),
    signal_type: requiredString(value, "signal_type"),
    category: requiredString(value, "category"),
    severity: requiredString(value, "severity"),
    title: requiredString(value, "title"),
    description: requiredString(value, "description"),
    status: requiredString(value, "status"),
    financial_impact_amount: impact === null ? null : moneyValue(impact),
    currency: typeof currency === "string" ? currency : null,
    customer_name: typeof customerName === "string" ? customerName : null,
    attention_group: parseGroup(value.attention_group),
    created_at: requiredString(value, "created_at"),
    action: parseAction(value.action),
  };
}

export function parseSignalDetail(value: unknown): SignalDetail {
  const signal = parseSignal(value);
  if (!isRecord(value)) {
    throw new Error("Expected a signal");
  }
  return {
    ...signal,
    timezone: requiredString(value, "timezone"),
    customer: parseCustomer(value.customer),
    commitment: parseCommitment(value.commitment),
    event: parseEvent(value.event),
    evidence: parseEvidence(value.evidence),
    conversation: parseConversationBrief(value.conversation),
  };
}

function parseGroup(value: unknown): AttentionGroup {
  if (value === "risk" || value === "opportunity" || value === "operations") {
    return value;
  }
  throw new Error("Missing attention group");
}

function parseCommitment(value: unknown): SignalDetail["commitment"] {
  if (value === null) {
    return null;
  }
  if (!isRecord(value)) {
    throw new Error("Expected a commitment");
  }
  const amount = value.amount;
  const currency = value.currency;
  const dueAt = value.due_at;
  const dueText = value.due_text;
  return {
    id: requiredString(value, "id"),
    commitment_type: requiredString(value, "commitment_type"),
    status: requiredString(value, "status"),
    amount: amount === null ? null : moneyValue(amount),
    currency: typeof currency === "string" ? currency : null,
    due_at: typeof dueAt === "string" ? dueAt : null,
    due_text: typeof dueText === "string" ? dueText : null,
    description: requiredString(value, "description"),
  };
}

function parseEvent(value: unknown): SignalDetail["event"] {
  if (value === null) {
    return null;
  }
  if (!isRecord(value)) {
    throw new Error("Expected an event");
  }
  const description = value.description;
  return {
    id: requiredString(value, "id"),
    event_type: requiredString(value, "event_type"),
    occurred_at: requiredString(value, "occurred_at"),
    description: typeof description === "string" ? description : null,
  };
}

function parseEvidence(value: unknown): SignalDetail["evidence"] {
  if (value === null) {
    return null;
  }
  if (!isRecord(value)) {
    throw new Error("Expected evidence");
  }
  return {
    message_id: requiredString(value, "message_id"),
    content: requiredString(value, "content"),
    sender_type: requiredString(value, "sender_type"),
    direction: requiredString(value, "direction"),
    occurred_at: requiredString(value, "occurred_at"),
    source: optionalText(value.source),
    source_label: optionalText(value.source_label),
    connection: optionalText(value.connection),
    external_message_id: optionalText(value.external_message_id),
  };
}

function parseAction(value: unknown): ActionBrief | null {
  if (value == null) {
    return null;
  }
  if (!isRecord(value)) {
    throw new Error("Expected an action");
  }
  return {
    id: requiredString(value, "id"),
    action_type: requiredString(value, "action_type"),
    title: optionalText(value.title),
    description: optionalText(value.description),
    status: requiredString(value, "status"),
    proposed_content: optionalText(value.proposed_content),
  };
}

function optionalText(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}
