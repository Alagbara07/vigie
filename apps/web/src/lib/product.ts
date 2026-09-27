import { formatMoney } from "@/lib/format";

export const PRODUCT_LINE =
  "VIGIE watches your business conversations, remembers important commitments and requests, and surfaces what needs your attention before it becomes a problem.";

type MoneySignal = {
  signal_type: string;
  title: string;
  description: string;
  financial_impact_amount: string | null;
  currency: string | null;
};

export function attentionHeadline(openSignals: number): string {
  if (openSignals === 1) {
    return "1 thing needs your attention";
  }
  return `${openSignals} things need your attention`;
}

export function countOpen(signals: { status: string; signal_type: string }[], signalType: string): number {
  return signals.filter((signal) => signal.status === "OPEN" && signal.signal_type === signalType).length;
}

export function whatHappened(signal: MoneySignal): string {
  if (signal.signal_type === "OVERDUE_PAYMENT" && signal.financial_impact_amount && signal.currency) {
    return `${formatMoney(signal.financial_impact_amount, signal.currency)} payment commitment was missed.`;
  }
  if (signal.signal_type === "UNANSWERED_REQUEST") {
    return "A customer request is still waiting for a reply.";
  }
  return signal.title;
}

export function whyItMatters(signal: MoneySignal): string {
  if (signal.signal_type === "OVERDUE_PAYMENT" && signal.financial_impact_amount && signal.currency) {
    const amount = formatMoney(signal.financial_impact_amount, signal.currency);
    return `This payment remains unresolved and represents ${amount} of revenue at risk.`;
  }
  if (signal.signal_type === "UNANSWERED_REQUEST") {
    return "This request is still waiting, and the business has not replied.";
  }
  return signal.description;
}

export function whyRecommendation(signal: {
  signal_type: string;
  financial_impact_amount: string | null;
  currency: string | null;
  description: string | null;
}): string {
  if (signal.signal_type === "OVERDUE_PAYMENT" && signal.financial_impact_amount && signal.currency) {
    const amount = formatMoney(signal.financial_impact_amount, signal.currency);
    return `VIGIE suggests this because a ${amount} payment commitment is overdue.`;
  }
  if (signal.signal_type === "UNANSWERED_REQUEST") {
    return "VIGIE suggests this because a customer request is still waiting for a reply.";
  }
  return signal.description ?? "Suggested from what VIGIE already found in this conversation.";
}

export function detectedAs(eventType: string): string {
  if (eventType === "PAYMENT_COMMITMENT") {
    return "Payment commitment";
  }
  if (eventType === "PAYMENT_CLAIM") {
    return "Payment claim";
  }
  if (eventType === "UNANSWERED_REQUEST") {
    return "Customer request";
  }
  const words = eventType.toLowerCase().split("_");
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}

export function stateLabel(status: string): string {
  if (status === "MISSED") {
    return "Missed";
  }
  if (status === "PENDING") {
    return "Pending";
  }
  if (status === "FULFILLED") {
    return "Fulfilled";
  }
  if (status === "OPEN") {
    return "Open";
  }
  if (status === "RESOLVED") {
    return "Resolved";
  }
  if (status === "PROPOSED") {
    return "Proposed";
  }
  if (status === "APPROVED") {
    return "Approved";
  }
  if (status === "REJECTED") {
    return "Rejected";
  }
  return status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
}

export function reachedSteps(signalType: string): string[] {
  if (signalType === "OVERDUE_PAYMENT") {
    return [
      "Conversation read",
      "Payment commitment found",
      "Commitment watched over time",
      "Deadline passed",
      "Flagged for your attention",
    ];
  }
  if (signalType === "UNANSWERED_REQUEST") {
    return [
      "Conversation read",
      "Customer request found",
      "Waiting for a reply",
      "Reply window passed",
      "Flagged for your attention",
    ];
  }
  return ["Conversation read", "Something that needs attention was found", "Flagged for your attention"];
}
