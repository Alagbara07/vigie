/// <reference types="vitest/globals" />
import { fireEvent, render, screen } from "@testing-library/react";

import { IntegrationsPanel } from "@/components/integrations-panel";
import { ApiError } from "@/lib/api/client";

const result = {
  created: true,
  analyzed: true,
  message_id: "message-1",
  source: "demo",
  source_label: "WhatsApp Business",
  connection: "Demo connection",
  customer_name: "Amaka Bello",
  text: "I'll pay the remaining ₦150,000 on Friday.",
  occurred_at: "2026-09-24T09:00:00+01:00",
  external_message_id: "demo-wa-001",
  events: ["PAYMENT_COMMITMENT"],
};

describe("integrations", () => {
  it("shows the prototype channels without live provider buttons", () => {
    render(<IntegrationsPanel demoEnabled onSend={async () => result} />);

    expect(screen.getByRole("heading", { name: "Connect your business channels" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "WhatsApp Business" })).toBeInTheDocument();
    expect(screen.getByText("Prototype")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Google Workspace" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Microsoft 365" })).toBeInTheDocument();
    expect(screen.getAllByText("Coming soon")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Coming soon" })).not.toBeInTheDocument();
    expect(screen.queryByText("WhatsApp Connected")).not.toBeInTheDocument();
  });

  it("opens the demo connection and sends a test message", async () => {
    const onSend = vi.fn(async () => result);
    render(<IntegrationsPanel demoEnabled onSend={onSend} />);

    fireEvent.click(screen.getByRole("button", { name: "Demo connection" }));
    expect(screen.getByText("Demo connection active")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Send to VIGIE" }));

    expect(await screen.findByText("Message received. VIGIE is analyzing the conversation.")).toBeInTheDocument();
    expect(onSend).toHaveBeenCalledWith({
      customerName: "Amaka Bello",
      text: "I'll pay the remaining ₦150,000 on Friday.",
    });
    expect(screen.getByText("Payment commitment detected")).toBeInTheDocument();
  });

  it("explains when the demo connector cannot receive the message", async () => {
    render(
      <IntegrationsPanel
        demoEnabled
        initiallyConnected
        onSend={async () => {
          throw new ApiError(503);
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Send to VIGIE" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("VIGIE couldn't receive that message. Please try again.");
  });

  it("keeps channel cards readable when dark mode is on", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    render(<IntegrationsPanel demoEnabled initiallyConnected onSend={async () => result} />);

    expect(screen.getByLabelText("Customer")).toHaveClass("bg-[var(--paper)]", "text-[var(--ink)]");
    expect(screen.getByLabelText("Message")).toHaveClass("bg-[var(--paper)]", "text-[var(--ink)]");
    document.documentElement.removeAttribute("data-theme");
  });
});
