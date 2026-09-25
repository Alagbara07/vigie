/// <reference types="vitest/globals" />
import { fireEvent, render, screen } from "@testing-library/react";

import { ActionReview } from "@/components/action-review";
import { ApiError } from "@/lib/api/client";
import type { ActionRecord } from "@/lib/api/actions";

const action: ActionRecord = {
  id: "action-1",
  business_id: "business-1",
  signal_id: "signal-1",
  action_type: "FOLLOW_UP_CUSTOMER",
  title: "Follow up with Amaka about the overdue ₦150,000 payment.",
  description: "Recommended because this payment commitment is past its due date and remains unfulfilled.",
  proposed_content: "Hi Amaka,\n\nJust following up on the ₦150,000 payment you mentioned.",
  status: "PROPOSED",
  approved_at: null,
  rejected_at: null,
  executed_at: null,
  signal: {
    id: "signal-1",
    title: "Payment overdue",
    signal_type: "OVERDUE_PAYMENT",
    financial_impact_amount: "150000.00",
    currency: "NGN",
  },
};

describe("action review", () => {
  it("opens the recommendation with the signal and the draft", () => {
    render(<ActionReview action={action} onApprove={async () => undefined} onReject={async () => undefined} />);

    expect(screen.getByRole("heading", { name: "Review action" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Why this action was recommended" })).toBeInTheDocument();
    expect(screen.getByText(/past its due date/)).toBeInTheDocument();
    expect(screen.getByText("Payment overdue")).toBeInTheDocument();
    expect(screen.getByText("₦150,000")).toBeInTheDocument();
    expect(screen.getByText(/Just following up on the ₦150,000 payment/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
  });

  it("shows that approval does not send a message", async () => {
    render(<ActionReview action={action} onApprove={async () => undefined} onReject={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(await screen.findByText("Action approved.")).toBeInTheDocument();
    expect(screen.getByText("No message has been sent.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("shows that the recommendation was rejected", async () => {
    render(<ActionReview action={action} onApprove={async () => undefined} onReject={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Reject" }));

    expect(await screen.findByText("Action rejected.")).toBeInTheDocument();
    expect(screen.queryByText("No message has been sent.")).not.toBeInTheDocument();
  });

  it("explains when the decision cannot be saved", async () => {
    render(
      <ActionReview
        action={action}
        onApprove={async () => {
          throw new ApiError();
        }}
        onReject={async () => undefined}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(await screen.findByRole("heading", { name: "VIGIE can't reach the intelligence service." })).toBeInTheDocument();
    expect(screen.getByText("Check that the API is running and try again.")).toBeInTheDocument();
  });
});
