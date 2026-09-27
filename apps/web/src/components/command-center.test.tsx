/// <reference types="vitest/globals" />
import { fireEvent, render, screen, within } from "@testing-library/react";

import { CommandCenter } from "@/components/command-center";
import { SignalDetailView } from "@/components/signal-detail";
import { DashboardSkeleton, ErrorNotice } from "@/components/states";
import type { DashboardSummary } from "@/lib/api/dashboard";
import type { SignalDetail, SignalRecord } from "@/lib/api/signals";

const now = new Date("2026-09-24T11:00:00+01:00");

const summary: DashboardSummary = {
  business_id: "business-1",
  business_name: "Adaeze Wears",
  timezone: "Africa/Lagos",
  currency: "NGN",
  open_signals: 2,
  high_priority_signals: 1,
  revenue_at_risk: "150000.00",
  missed_commitments: 1,
  opportunity_signals: 0,
  recent_conversations: [
    {
      conversation_id: "conversation-1",
      customer_id: "customer-1",
      customer_name: "Amaka Bello",
      last_message: "I'll pay the remaining ₦150,000 on Friday.",
      last_message_at: "2026-09-22T10:00:00Z",
      sender_type: "customer",
      direction: "inbound",
    },
  ],
};

const overdue: SignalRecord = {
  id: "signal-overdue",
  business_id: "business-1",
  signal_type: "OVERDUE_PAYMENT",
  category: "REVENUE",
  severity: "HIGH",
  title: "Payment overdue",
  description: "Amaka Bello promised NGN 150000 by Friday. The commitment has not been fulfilled.",
  status: "OPEN",
  financial_impact_amount: "150000.00",
  currency: "NGN",
  customer_name: "Amaka Bello",
  attention_group: "risk",
  created_at: "2026-09-24T09:00:00+01:00",
  action: null,
};

const request: SignalRecord = {
  id: "signal-request",
  business_id: "business-1",
  signal_type: "UNANSWERED_REQUEST",
  category: "OPERATIONS",
  severity: "MEDIUM",
  title: "Unanswered request",
  description: "Customer asked for the wholesale price and is waiting for a reply. The business has not replied.",
  status: "OPEN",
  financial_impact_amount: null,
  currency: null,
  customer_name: "Ngozi Eze",
  attention_group: "operations",
  created_at: "2026-09-24T10:00:00+01:00",
  action: null,
};

describe("command center", () => {
  it("renders backend summary figures and both severities", () => {
    render(<CommandCenter summary={summary} signals={[overdue, request]} now={now} />);

    const figures = screen.getByRole("region", { name: "2 things need your attention" });
    expect(screen.getByRole("heading", { name: "Good morning, Adaeze." })).toBeInTheDocument();
    expect(screen.getByText(/watches your business conversations/)).toBeInTheDocument();
    expect(within(figures).getByText("Revenue at risk").previousElementSibling).toHaveTextContent("₦150,000");
    expect(within(figures).getByText("Overdue payment").previousElementSibling).toHaveTextContent("1");
    expect(within(figures).getByText("Customer request waiting").previousElementSibling).toHaveTextContent("1");
    expect(screen.getByRole("heading", { name: "Payment overdue" })).toBeInTheDocument();
    expect(screen.getByText("₦150,000 payment commitment was missed.")).toBeInTheDocument();
    expect(screen.getByText(/₦150,000 of revenue at risk/)).toBeInTheDocument();
    expect(screen.getByText("Medium")).toBeInTheDocument();
    expect(screen.getAllByText("Amaka Bello").length).toBeGreaterThan(0);
  });

  it("filters risks without hiding the summary", () => {
    render(<CommandCenter summary={summary} signals={[overdue, request]} now={now} />);
    fireEvent.click(within(screen.getByRole("group", { name: "Signal kind" })).getByRole("button", { name: "Risks" }));

    expect(screen.getByRole("heading", { name: "Payment overdue" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Unanswered request" })).not.toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "2 things need your attention" })).getByText("Revenue at risk")
        .previousElementSibling,
    ).toHaveTextContent("₦150,000");
  });

  it("shows the caught-up state when nothing is open", () => {
    render(
      <CommandCenter
        summary={{ ...summary, open_signals: 0, high_priority_signals: 0, revenue_at_risk: "0", missed_commitments: 0 }}
        signals={[]}
        now={now}
      />,
    );

    expect(screen.getByRole("heading", { name: "You're all caught up." })).toBeInTheDocument();
    expect(screen.getByText("VIGIE isn't seeing anything that requires your attention right now.")).toBeInTheDocument();
  });

  it("renders a recommendation on the signal that has one", () => {
    render(
      <CommandCenter
        summary={summary}
        signals={[
          {
            ...overdue,
            action: {
              id: "action-1",
              action_type: "FOLLOW_UP_CUSTOMER",
              title: "Follow up with Amaka about the overdue ₦150,000 payment.",
              description: "Recommended because this payment commitment is past its due date and remains unfulfilled.",
              status: "PROPOSED",
              proposed_content: "Hi Amaka,",
            },
          },
        ]}
        now={now}
      />,
    );

    expect(screen.getByText("Recommended")).toBeInTheDocument();
    expect(screen.getByText("Proposed")).toBeInTheDocument();
    expect(screen.getByText("Follow up with Amaka about the overdue ₦150,000 payment.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review" })).toHaveAttribute(
      "href",
      "/actions/action-1?business_id=business-1",
    );
  });
});

describe("signal detail", () => {
  it("shows the commitment, the missed state, and the original message", () => {
    const detail: SignalDetail = {
      ...overdue,
      timezone: "Africa/Lagos",
      customer: {
        id: "customer-1",
        name: "Amaka Bello",
        status: "ACTIVE",
        created_at: "2026-09-24T12:00:00Z",
      },
      commitment: {
        id: "commitment-1",
        commitment_type: "PAYMENT_COMMITMENT",
        status: "MISSED",
        amount: "150000.00",
        currency: "NGN",
        due_at: "2026-09-25T00:00:00+01:00",
        due_text: "Friday",
        description: "Customer promised to pay NGN 150000 on Friday.",
      },
      event: {
        id: "event-1",
        event_type: "PAYMENT_COMMITMENT",
        occurred_at: "2026-09-22T10:00:00Z",
        description: "Customer promised to pay NGN 150000 on Friday.",
      },
      evidence: {
        message_id: "message-1",
        content: "I'll pay the remaining ₦150,000 on Friday.",
        sender_type: "customer",
        direction: "inbound",
        occurred_at: "2026-09-22T10:00:00Z",
      },
      conversation: { id: "conversation-1", channel: "simulated", message_count: 1 },
      action: null,
    };

    render(<SignalDetailView detail={detail} />);

    expect(screen.getByText("Payment commitment")).toBeInTheDocument();
    expect(screen.getByText("Missed")).toBeInTheDocument();
    expect(screen.getByText("Friday")).toBeInTheDocument();
    expect(screen.getByText(/I'll pay the remaining ₦150,000 on Friday/)).toBeInTheDocument();
    expect(screen.getByText("Customer message")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How VIGIE reached this" })).toBeInTheDocument();
    expect(screen.getByText("Deadline passed")).toBeInTheDocument();
    expect(screen.getAllByText("Amaka Bello")).toHaveLength(2);
    expect(screen.getByText("1 message")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Recommended action" })).not.toBeInTheDocument();
  });

  it("shows the channel on the evidence when the message has a source", () => {
    const detail: SignalDetail = {
      ...overdue,
      timezone: "Africa/Lagos",
      customer: {
        id: "customer-1",
        name: "Amaka Bello",
        status: "ACTIVE",
        created_at: "2026-09-24T12:00:00Z",
      },
      evidence: {
        message_id: "message-1",
        content: "I'll pay the remaining ₦150,000 on Friday.",
        sender_type: "customer",
        direction: "inbound",
        occurred_at: "2026-09-24T08:00:00Z",
        source: "demo",
        source_label: "WhatsApp Business",
        connection: "Demo connection",
        external_message_id: "demo-wa-001",
      },
      commitment: null,
      event: null,
      conversation: null,
    };

    render(<SignalDetailView detail={detail} />);

    expect(screen.getByText("WhatsApp Business")).toBeInTheDocument();
    expect(screen.getByText("Demo connection")).toBeInTheDocument();
    expect(screen.getByText("External message demo-wa-001")).toBeInTheDocument();
    expect(screen.queryByText("WhatsApp Connected")).not.toBeInTheDocument();
  });

  it("shows a recommendation after the evidence and links to review", () => {
    const detail: SignalDetail = {
      ...overdue,
      timezone: "Africa/Lagos",
      customer: null,
      commitment: null,
      event: null,
      evidence: {
        message_id: "message-1",
        content: "I'll pay the remaining ₦150,000 on Friday.",
        sender_type: "customer",
        direction: "inbound",
        occurred_at: "2026-09-22T10:00:00Z",
      },
      conversation: null,
      action: {
        id: "action-1",
        action_type: "FOLLOW_UP_CUSTOMER",
        title: "Follow up with Amaka about the overdue ₦150,000 payment.",
        description: "Recommended because this payment commitment is past its due date and remains unfulfilled.",
        status: "PROPOSED",
        proposed_content: "Hi Amaka,\n\nJust following up.",
      },
    };

    render(<SignalDetailView detail={detail} />);

    const evidence = screen.getByText(/I'll pay the remaining/);
    const recommendation = screen.getByRole("heading", { name: "Recommended action" });
    expect(evidence.compareDocumentPosition(recommendation) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText("Follow up with Amaka about the overdue ₦150,000 payment.")).toBeInTheDocument();
    expect(screen.getByText("Proposed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review" })).toHaveAttribute(
      "href",
      "/actions/action-1?business_id=business-1",
    );
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });
});

describe("loading and error states", () => {
  it("uses a skeleton while the command center is loading", () => {
    render(<DashboardSkeleton />);
    expect(screen.getByText("Checking what needs attention")).toBeInTheDocument();
    expect(screen.queryByText("Loading...")).not.toBeInTheDocument();
  });

  it("explains a failed load without a raw server error", () => {
    render(<ErrorNotice onRetry={() => undefined} />);
    expect(screen.getByRole("heading", { name: "VIGIE couldn't load your signals." })).toBeInTheDocument();
    expect(screen.getByText("Please try again.")).toBeInTheDocument();
    expect(screen.queryByText(/500/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
