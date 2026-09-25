import { apiGet, apiPost, isRecord, moneyValue, requiredString } from "@/lib/api/client";
import type { ActionBrief } from "@/lib/api/signals";

export type ActionRecord = ActionBrief & {
  business_id: string;
  signal_id: string;
  approved_at: string | null;
  rejected_at: string | null;
  executed_at: string | null;
  signal: {
    id: string;
    title: string;
    signal_type: string;
    financial_impact_amount: string | null;
    currency: string | null;
  };
};

export function recommendActions(businessId: string, signalId?: string): Promise<void> {
  return apiPost(
    "/api/actions/recommend",
    signalId ? { business_id: businessId, signal_id: signalId } : { business_id: businessId },
    () => undefined,
  );
}

export function loadAction(actionId: string, businessId: string): Promise<ActionRecord> {
  return apiGet(`/api/actions/${actionId}?business_id=${businessId}`, parseActionRecord);
}

export function approveAction(actionId: string, businessId: string): Promise<ActionRecord> {
  return apiPost(`/api/actions/${actionId}/approve`, { business_id: businessId }, parseActionRecord);
}

export function rejectAction(actionId: string, businessId: string): Promise<ActionRecord> {
  return apiPost(`/api/actions/${actionId}/reject`, { business_id: businessId }, parseActionRecord);
}

export function actionHref(actionId: string, businessId: string): string {
  return `/actions/${actionId}?business_id=${businessId}`;
}

export function parseActionRecord(value: unknown): ActionRecord {
  if (!isRecord(value) || !isRecord(value.signal)) {
    throw new Error("Expected an action");
  }
  const impact = value.signal.financial_impact_amount;
  const currency = value.signal.currency;
  return {
    id: requiredString(value, "id"),
    business_id: requiredString(value, "business_id"),
    signal_id: requiredString(value, "signal_id"),
    action_type: requiredString(value, "action_type"),
    title: optionalText(value.title),
    description: optionalText(value.description),
    status: requiredString(value, "status"),
    proposed_content: optionalText(value.proposed_content),
    approved_at: optionalText(value.approved_at),
    rejected_at: optionalText(value.rejected_at),
    executed_at: optionalText(value.executed_at),
    signal: {
      id: requiredString(value.signal, "id"),
      title: requiredString(value.signal, "title"),
      signal_type: requiredString(value.signal, "signal_type"),
      financial_impact_amount: impact === null || impact === undefined ? null : moneyValue(impact),
      currency: typeof currency === "string" ? currency : null,
    },
  };
}

function optionalText(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}
