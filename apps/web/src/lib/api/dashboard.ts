import { apiGet, isRecord, moneyValue, requiredNumber, requiredString } from "@/lib/api/client";
import { parseConversationPreview, type ConversationPreview } from "@/lib/api/conversations";

export type DashboardSummary = {
  business_id: string;
  business_name: string;
  timezone: string;
  currency: string;
  open_signals: number;
  high_priority_signals: number;
  revenue_at_risk: string;
  missed_commitments: number;
  opportunity_signals: number;
  recent_conversations: ConversationPreview[];
};

export function loadDashboardSummary(businessId: string): Promise<DashboardSummary> {
  return apiGet(`/api/dashboard/summary?business_id=${businessId}`, parseDashboardSummary);
}

export function parseDashboardSummary(value: unknown): DashboardSummary {
  if (!isRecord(value) || !Array.isArray(value.recent_conversations)) {
    throw new Error("Expected a dashboard summary");
  }
  return {
    business_id: requiredString(value, "business_id"),
    business_name: requiredString(value, "business_name"),
    timezone: requiredString(value, "timezone"),
    currency: requiredString(value, "currency"),
    open_signals: requiredNumber(value, "open_signals"),
    high_priority_signals: requiredNumber(value, "high_priority_signals"),
    revenue_at_risk: moneyValue(value.revenue_at_risk),
    missed_commitments: requiredNumber(value, "missed_commitments"),
    opportunity_signals: requiredNumber(value, "opportunity_signals"),
    recent_conversations: value.recent_conversations.map(parseConversationPreview),
  };
}
